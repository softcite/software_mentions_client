'''
    Run the software mention recognizer service on PDF collections
'''

import gzip
import sys
import os
import shutil
import json
import pickle
import lmdb
import argparse
import time
import datetime
from software_mentions_client import S3
import concurrent.futures
import requests
import pymongo
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import hashlib
import copyreg
import types
import logging
import logging.handlers

map_size = 100 * 1024 * 1024 * 1024 

# default endpoint
endpoint_pdf = 'service/annotateSoftwarePDF'
endpoint_txt = 'service/annotateSoftwareText'

# default logging settings
logging.basicConfig(filename='client.log', filemode='w', level=logging.DEBUG)

class software_mentions_client(object):
    """
    Python client for using the Softcite software mention service. 
    """

    def __init__(self, config_path='./config.json'):
        self.config = None
        
        # standard lmdb environment for keeping track of the status of processing
        self.env_software = None

        self._load_config(config_path)
        self._init_lmdb()

        if self.config['bucket_name'] is not None and len(self.config['bucket_name']) > 0:
            self.s3 = S3.S3(self.config)

        self.mongo_db = None

        # load blacklist 
        self.blacklisted = []
        with open ("resources/covid_blacklist.txt", "r") as blackfile:
            for line in blackfile:
                line = line.replace(" ", "").strip()
                if not line.startswith("#"):
                    self.blacklisted.append(line)
        logging.info("blacklist size: " + str(len(self.blacklisted)))

        self.scorched_earth = False

        logs_filename = "client.log"
        if "log_file" in self.config: 
            logs_filename = self.config['log_file']

        logs_level = logging.DEBUG
        if "log_level" in self.config:
            if self.config["log_level"] == 'INFO':
                logs_level = logging.INFO
            elif self.config["log_level"] == 'ERROR':
                logs_level = logging.ERROR
            elif self.config["log_level"] == 'WARNING':
                logs_level = logging.WARNING
            elif self.config["log_level"] == 'CRITICAL':
                logs_level = logging.CRITICAL
            else:
                logs_level = logging.NOTSET
        logging.basicConfig(filename=logs_filename, filemode='w', level=logs_level)
        print("logs are written in " + logs_filename)

    def _load_config(self, path='./config.json'):
        """
        Load the json configuration 
        """
        config_json = open(path).read()
        self.config = json.loads(config_json)
        if not "timeout" in self.config:
            # this is the default value for a service timeout
            self.config["timeout"] = 600

    def service_isalive(self):
        # test if Softcite software mention recognizer is up and running...
        the_url = f'http://{self.config["software_mention_host"]}:{self.config["software_mention_port"]}'
        if not the_url.endswith("/"):
            the_url += "/"
        the_url += "service/isalive"
        try:
            r = requests.get(the_url)

            if r.status_code != 200:
                logging.error('Softcite software mention server does not appear up and running ' + str(r.status_code))
            else:
                logging.info("Softcite software mention server is up and running")
                return True
        except: 
            logging.error('Softcite software mention server does not appear up and running: ' + 
                'test call to Softcite software mention failed, please check and re-start a server.')
        return False

    def _init_lmdb(self):
        # open in write mode
        envFilePath = os.path.join(self.config["data_path"], 'entries_software')
        self.env_software = lmdb.open(envFilePath, map_size=map_size)

        #envFilePath = os.path.join(self.config["data_path"], 'fail_software')
        #self.env_fail_software = lmdb.open(envFilePath, map_size=map_size)

    def annotate_directory(self, directory, force=False):
        # recursive directory walk for all pdf documents
        pdf_files = []
        out_files = []
        full_records = []
        nb_total = 0
        start_time = time.time()

        print("\n")
        sys.stdout.write("\rtotal process: " + str(nb_total) + " - accumulated runtime: 0 s - 0 PDF/s")
        sys.stdout.flush()

        for root, directories, filenames in os.walk(directory):
            for filename in filenames:
                if filename.endswith(".pdf") or filename.endswith(".PDF") or filename.endswith(".pdf.gz"):
                    if filename.endswith(".pdf"):
                        filename_json = filename.replace(".pdf", ".software.json")
                    elif filename.endswith(".pdf.gz"):
                        filename_json = filename.replace(".pdf.gz", ".software.json")
                    elif filename.endswith(".PDF"):
                        filename_json = filename.replace(".PDF", ".software.json")

                    sha1 = getSHA1(os.path.join(root,filename))

                    # if the json file already exists and not force, we skip 
                    if os.path.isfile(os.path.join(root, filename_json)) and not force:
                        # check that this id is considered in the lmdb keeping track of the process
                        with self.env_software.begin() as txn:
                            status = txn.get(sha1.encode(encoding='UTF-8'))
                        if status is None:
                            with self.env_software.begin(write=True) as txn2:
                                txn2.put(sha1.encode(encoding='UTF-8'), "True".encode(encoding='UTF-8')) 
                        continue

                    # if identifier already processed successfully in the local lmdb, we skip
                    # the hash of the PDF file is used as unique identifier for the PDF (SHA1)
                    with self.env_software.begin() as txn:
                        status = txn.get(sha1.encode(encoding='UTF-8'))
                        if status is not None and not force:
                            continue

                    pdf_files.append(os.path.join(root,filename))
                    out_files.append(os.path.join(root, filename_json))
                    record = {}
                    record["id"] = sha1
                    full_records.append(record)
                    
                    if len(pdf_files) == self.config["batch_size"]:
                        self.annotate_batch(pdf_files, out_files, full_records)
                        nb_total += len(pdf_files)
                        pdf_files = []
                        out_files = []
                        full_records = []
                        runtime = round(time.time() - start_time, 3)
                        sys.stdout.write("\rtotal process: " + str(nb_total) + " - accumulated runtime: " + str(runtime) + " s - " + str(round(nb_total/runtime, 2)) + " PDF/s  ")
                        sys.stdout.flush()
        # last batch
        if len(pdf_files) > 0:
            self.annotate_batch(pdf_files, out_files, full_records)
            nb_total += len(pdf_files)
            runtime = round(time.time() - start_time, 3)
            sys.stdout.write("\rtotal process: " + str(nb_total) + " - accumulated runtime: " + str(runtime) + " s - " + str(round(nb_total/runtime, 2)) + " PDF/s  ")
            sys.stdout.flush()

    def annotate_collection(self, data_path, force=False):
        # init lmdb transactions
        # open in read mode
        envFilePath = os.path.join(data_path, 'entries')
        self.env = lmdb.open(envFilePath, map_size=map_size)

        with self.env.begin(write=True) as txn:
            nb_total = txn.stat()['entries']
        print("\nnumber of entries to process:", nb_total, "entries\n")

        # iterate over the entries in lmdb
        pdf_files = []
        out_files = []
        full_records = []
        nb_total = 0
        start_time = time.time()

        sys.stdout.write("\rtotal process: " + str(nb_total) + " - accumulated runtime: 0 s - 0 PDF/s")
        sys.stdout.flush()

        with self.env.begin(write=True) as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                local_entry = _deserialize_pickle(value)
                local_entry["id"] = key.decode(encoding='UTF-8');
                #print(local_entry)

                # if the json file already exists and not force, we skip 
                json_outfile = os.path.join(os.path.join(data_path, generateStoragePath(local_entry['id']), local_entry['id'], local_entry['id']+".software.json"))
                if os.path.isfile(json_outfile) and not force:
                    # check that this id is considered in the lmdb keeping track of the process
                    with self.env_software.begin() as txn:
                        status = txn.get(local_entry['id'].encode(encoding='UTF-8'))
                    if status is None:
                        with self.env_software.begin(write=True) as txn2:
                            txn2.put(local_entry['id'].encode(encoding='UTF-8'), "True".encode(encoding='UTF-8')) 
                    continue

                # if identifier already processed in the local lmdb (successfully or not) and not force, we skip this file
                with self.env_software.begin() as txn:
                    status = txn.get(local_entry['id'].encode(encoding='UTF-8'))
                    if status is not None and not force:
                        continue

                pdf_files.append(os.path.join(data_path, generateStoragePath(local_entry['id']), local_entry['id'], local_entry['id']+".pdf"))
                out_files.append(json_outfile)
                full_records.append(local_entry)

                if len(pdf_files) == self.config["batch_size"]:
                    self.annotate_batch(pdf_files, out_files, full_records)
                    nb_total += len(pdf_files)
                    pdf_files = []
                    out_files = []
                    full_records = []
                    runtime = round(time.time() - start_time, 3)
                    sys.stdout.write("\rtotal process: " + str(nb_total) + " - accumulated runtime: " + str(runtime) + " s - " + str(round(nb_total/runtime, 2)) + " PDF/s  ")
                    sys.stdout.flush()

        # last batch
        if len(pdf_files) > 0:
            self.annotate_batch(pdf_files, out_files, full_records)
            runtime = round(time.time() - start_time, 3)
            sys.stdout.write("\rtotal process: " + str(nb_total) + " - accumulated runtime: " + str(runtime) + " s - " + str(round(nb_total/runtime, 2)) + " PDF/s  ")
            sys.stdout.flush()

    def annotate_batch(self, pdf_files, out_files=None, full_records=None):
        # process a provided list of PDF
        with ThreadPoolExecutor(max_workers=self.config["concurrency"]) as executor:
            #with ProcessPoolExecutor(max_workers=self.config["concurrency"]) as executor:
            # note: ProcessPoolExecutor will not work due to env objects that can't be serailized (e.g. LMDB variables)
            # client is not cpu bounded but io bounded, so normally it's still okay with threads and GIL
            executor.map(self.annotate, pdf_files, out_files, full_records, timeout=self.config["timeout"])

    def reprocess_failed(self):
        """
        we reprocess only files which have led to a failure of the service, we don't reprocess documents
        where no software mention has been found 
        """
        pdf_files = []
        out_files = []
        full_records = []
        i = 0
        nb_total = 0
        with self.env_software.begin() as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                nb_total += 1
                result = value.decode(encoding='UTF-8')
                local_id = key.decode(encoding='UTF-8')
                if result == "False":
                    # reprocess
                    logging.info("reprocess " + local_id)
                    pdf_files.append(os.path.join(data_path, generateStoragePath(local_id), local_id, local_id+".pdf"))
                    out_files.append(os.path.join(data_path, generateStoragePath(local_id), local_id, local_id+".software.json"))
                    # get the full record from the data_path env
                    json_file = os.path.join(data_path, generateStoragePath(local_id), local_id, local_id+".json")
                    if os.path.isfile(json_file):
                        with open(json_file) as f:
                            full_record = json.load(f)
                        full_records.append(full_record)
                    i += 1

            if i == self.config["batch_size"]:
                self.annotate_batch(pdf_files, out_files, full_records)
                pdf_files = []
                out_files = []
                full_records = []
                i = 0

        # last batch
        if len(pdf_files) > 0:
            self.annotate_batch(pdf_files, out_files, full_records)

        logging.info("re-processed: " + str(nb_total) + " entries")

    def reset(self):
        """
        Remove the local lmdb keeping track of the state of advancement of the annotation and
        of the failed entries
        """
        # close environments
        self.env_software.close()

        envFilePath = os.path.join(self.config["data_path"], 'entries_software')
        shutil.rmtree(envFilePath)

        # re-init the environments
        self._init_lmdb()

    def load_mongo(self, directory):
        if "mongo_host" in self.config and len(self.config["mongo_host"].strip())>0:
            mongo_client = pymongo.MongoClient(self.config["mongo_host"], int(self.config["mongo_port"]))
            self.mongo_db = mongo_client[self.config["mongo_db"]]
        if self.mongo_db == None:
            return

        failed = 0
        for root, directories, filenames in os.walk(directory):
            for filename in filenames: 
                if filename.endswith(".software.json"):
                    #print(os.path.join(root,filename))
                    the_json = open(os.path.join(root,filename)).read()
                    try:
                        jsonObject = json.loads(the_json)
                    except:
                        print("the json parsing of the following file failed: ", os.path.join(root,filename))
                        continue

                    local_id = None
                    if not 'id' in jsonObject:
                        ind = filename.find(".")
                        if ind != -1:
                            local_id = filename[:ind]
                            jsonObject['id'] = local_id
                    else:
                        local_id = jsonObject['id']

                    if local_id == None:
                        continue

                    # no mention, no insert
                    if not 'mentions' in jsonObject or len(jsonObject['mentions']) == 0:
                        continue

                    # possibly clean original file path
                    if "original_file_path" in jsonObject:
                        if jsonObject["original_file_path"].startswith('../biblio-glutton-harvester/'):
                            jsonObject["original_file_path"] = jsonObject["original_file_path"].replace('../biblio-glutton-harvester/', '')
                    
                    # update metadata via biblio-glutton (this is to be done for mongo upload from file only)
                    if "biblio_glutton_url" in self.config and len(self.config["biblio_glutton_url"].strip())>0:
                        if 'metadata' in jsonObject and 'doi' in jsonObject['metadata']: 
                            try:
                                glutton_metadata = self.biblio_glutton_lookup(doi=jsonObject['metadata']['doi'])
                            except: 
                                print("the call to biblio-glutton failed for", jsonObject['metadata']['doi'])
                                failed += 1
                                continue
                            if glutton_metadata != None:
                                # update/complete document metadata
                                glutton_metadata['id'] = local_id
                                if 'best_oa_location' in jsonObject['metadata']:
                                    glutton_metadata['best_oa_location'] = jsonObject['metadata']['best_oa_location']
                                jsonObject['metadata'] = glutton_metadata
                                self._insert_mongo(jsonObject)
                            else:
                                failed += 1
                        else:
                            failed += 1

        print("number of glutton metadata lookup failed:", failed)

    def annotate(self, file_in, file_out, full_record):
        try:
            if file_in.endswith('.pdf.gz'):
                the_file = {'input': gzip.open(file_in, 'rb')}
            else:
                the_file = {'input': open(file_in, 'rb')}
        except:
            logging.exception("input file appears invalid: " + file_in)
            return

        url = f'http://{self.config["software_mention_host"]}:{self.config["software_mention_port"]}'
        if not url.endswith("/"):
            url += "/"
        url += endpoint_pdf
        
        jsonObject = None
        try:
            response = requests.post(url, files=the_file, data = {'disambiguate': 1}, timeout=self.config["timeout"])
            if response.status_code == 503:
                logging.info('service overloaded, sleep ' + str(self.config['sleep_time']) + ' seconds')
                time.sleep(self.config['sleep_time'])
                return self.annotate(file_in, self.config, file_out, full_record)
            elif response.status_code >= 500:
                logging.error('[{0}] Server Error '.format(response.status_code) + file_in)
            elif response.status_code == 404:
                logging.error('[{0}] URL not found: [{1}] '.format(response.status_code + url))
            elif response.status_code >= 400:
                logging.error('[{0}] Bad Request'.format(response.status_code))
                logging.error(response.content)
            elif response.status_code == 200:
                jsonObject = response.json()
                # note: in case the recognizer has found no software in the document, it will still return
                # a json object as result, without mentions, but with MD5 and page information
            else:
                logging.error('Unexpected Error: [HTTP {0}]: Content: {1}'.format(response.status_code, response.content))

        except requests.exceptions.Timeout:
            logging.exception("The request to the annotation service has timeout")
        except requests.exceptions.TooManyRedirects:
            logging.exception("The request failed due to too many redirects")
        except requests.exceptions.RequestException:
            logging.exception("The request failed")

        # at this stage, if jsonObject is still at None, the process failed 
        if jsonObject is not None and 'mentions' in jsonObject and len(jsonObject['mentions']) > 0:
            # we have found software mentions in the document
            # add file, DOI, date and version info in the JSON, if available
            if full_record is not None:
                jsonObject['id'] = full_record['id']
                #if len(full_record) > 1:
                jsonObject['metadata'] = full_record;
            jsonObject['original_file_path'] = file_in
            jsonObject['file_name'] = os.path.basename(file_in)

            # apply blacklist
            new_mentions = []
            if 'mentions' in jsonObject:
                for mention in jsonObject['mentions']:
                    if "software-name" in mention:
                        software_name = mention["software-name"]
                        normalizedForm = software_name["normalizedForm"]
                        normalizedForm = normalizedForm.replace(" ", "").strip()
                        if normalizedForm not in self.blacklisted:
                            new_mentions.append(mention)
                jsonObject['mentions'] = new_mentions

            if file_out is not None: 
                # we write the json result into a file together with the processed pdf
                with open(file_out, "w", encoding="utf-8") as json_file:
                    json_file.write(json.dumps(jsonObject))

            if "mongo_host" in self.config and len(self.config["mongo_host"].strip()) > 0:
                # we store the result in mongo db 
                self._insert_mongo(jsonObject)
        elif jsonObject is not None:
            # we have no software mention in the document, we still write an empty result file
            # along with the PDF/medtadata files to easily keep track of the processing for this doc
            if file_out is not None: 
                # force empty explicit no mentions
                jsonObject['mentions'] = []
                with open(file_out, "w", encoding="utf-8") as json_file:
                    json_file.write(json.dumps(jsonObject))

        # for keeping track of the processing
        # update processed entry in the lmdb (having entities or not) and failure
        if self.env_software is not None and full_record is not None:
            with self.env_software.begin(write=True) as txn:
                if jsonObject is not None:
                    txn.put(full_record['id'].encode(encoding='UTF-8'), "True".encode(encoding='UTF-8')) 
                else:
                    # the process failed
                    txn.put(full_record['id'].encode(encoding='UTF-8'), "False".encode(encoding='UTF-8'))

        if self.scorched_earth and jsonObject is not None:
            # processed is done, remove local PDF file
            try:
                os.remove(file_in) 
            except:
                logging.exception("Error while deleting file " + file_in)

    def diagnostic(self, full_diagnostic=False):
        """
        Print a report on failures stored during the harvesting process
        """
        nb_total = 0
        nb_fail = 0
        nb_success = 0  

        with self.env_software.begin() as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                nb_total += 1
                result = value.decode(encoding='UTF-8')
                if result == "True":
                    nb_success += 1
                else:
                    nb_fail += 1

        print("\n\n---")
        print("total entries:", nb_total)
        print("---")
        print("total successfully processed:", nb_success)
        print("---")
        print("total failed:", nb_fail)
        print("---")

        if full_diagnostic:
            # check mongodb access - if mongodb is not used or available, we don't go further
            if self.mongo_db is None:
                if "mongo_host" in self.config and len(self.config["mongo_host"].strip())>0:
                    mongo_client = pymongo.MongoClient(self.config["mongo_host"], int(self.config["mongo_port"]))
                    self.mongo_db = mongo_client[self.config["mongo_db"]]

            if self.mongo_db is None:
                print("MongoDB server is not available")    
                return

            print("MongoDB - number of documents: ", self.mongo_db.documents.count_documents({}))
            print("MongoDB - number of software mentions: ", self.mongo_db.annotations.count_documents({}))

            result = self.mongo_db.annotations.find( {"software-name": {"$exists": True}} )
            print("\t  * with software name:", result.count())
 
            result = self.mongo_db.annotations.find( {"version": {"$exists": True}} )
            print("\t  * with version:", result.count())

            result = self.mongo_db.annotations.find( {"publisher": {"$exists": True}} )
            print("\t  * with publisher:", result.count())

            result = self.mongo_db.annotations.find( {"url": {"$exists": True}} )
            print("\t  * with url:", result.count())    

            results = self.mongo_db.annotations.find( {"references": {"$exists": True}} )
            nb_ref = 0
            has_ref = 0
            for result in results:
                has_ref += 1
                the_references = result.get("references")
                nb_ref += len(the_references)
                    
            print("\t  * with at least one reference", nb_ref) 
            print("\t  * total references", nb_ref) 

            print("MongoDB - number of bibliographical references: ", self.mongo_db.references.count_documents({}))

            result = self.mongo_db.references.find( {"tei": {"$regex": "DOI"}} )
            print("\t  * with DOI:", result.count())  

            result = self.mongo_db.references.find( {"tei": {"$regex": "PMID"}} )
            print("\t  * with PMID:", result.count())  

            result = self.mongo_db.references.find( {"tei": {"$regex": "PMC"}} )
            print("\t  * with PMC ID:", result.count())  
            print("---")

    def _insert_mongo(self, jsonObject):
        if self.mongo_db is None:
            mongo_client = pymongo.MongoClient(self.config["mongo_host"], int(self.config["mongo_port"]))
            self.mongo_db = mongo_client[self.config["mongo_db"]]

        if self.mongo_db is None:
            return

        # check if the article/annotations are not already present
        if self.mongo_db.documents.count_documents({ 'id': jsonObject['id'] }, limit = 1) != 0:
            # if yes we replace this object, its annotations and references
            result = self.mongo_db.documents.find_one({ 'id': jsonObject['id'] })
            _id = result['_id']
            self.mongo_db.annotations.delete_many( {'document': _id} )
            self.mongo_db.references.delete_many( {'document': _id} )
            result = self.mongo_db.documents.delete_one({ 'id': jsonObject['id'] })
            #print ("result:", type(result), "-- deleted count:", result.deleted_count)
        
        # clean json
        jsonObject = _clean_json(jsonObject)

        # deep copy of the json object
        jsonObjectDocument = json.loads(json.dumps(jsonObject))
        if 'mentions' in jsonObjectDocument:
            del jsonObjectDocument['mentions']
        if 'references' in jsonObjectDocument:
            del jsonObjectDocument['references']
        inserted_doc_id = self.mongo_db.documents.insert_one(jsonObjectDocument).inserted_id
        
        local_ref_map = {}
        if 'references' in jsonObject:
            for reference in jsonObject['references']:
                reference["document"] = inserted_doc_id
                inserted_reference_id = self.mongo_db.references.insert_one(reference).inserted_id
                local_ref_map[str(reference["refKey"])] = inserted_reference_id

        if 'mentions' in jsonObject:
            for mention in jsonObject['mentions']:
                mention["document"] = inserted_doc_id
                # insert the mongodb id of the stored references
                if "references" in mention:
                    for reference in mention["references"]:
                        if str(reference["refKey"]) in local_ref_map:
                            reference["reference_id"] = local_ref_map[str(reference["refKey"])]
                inserted_mention_id = self.mongo_db.annotations.insert_one(mention).inserted_id


    def biblio_glutton_lookup(self, doi=None, pmcid=None, pmid=None, istex_id=None, istex_ark=None):
        """
        Lookup on biblio_glutton with the provided strong identifiers, return the full agregated biblio_glutton record
        """
        print("biblio_glutton_lookup")

        success = False
        jsonResult = None

        if "biblio_glutton_url" in self.config and len(self.config["biblio_glutton_url"].strip()) > 0:
            biblio_glutton_url = self.config["biblio_glutton_url"]+"/service/lookup?"

            if doi is not None and len(doi)>0:
                response = requests.get(biblio_glutton_url, params={'doi': doi}, verify=False, timeout=5)
                success = (response.status_code == 200)
                if success:
                    jsonResult = response.json()

            if not success and pmid is not None and len(pmid)>0:
                response = requests.get(biblio_glutton_url + "pmid=" + pmid, verify=False, timeout=5)
                success = (response.status_code == 200)
                if success:
                    jsonResult = response.json()     

            if not success and pmcid is not None and len(pmcid)>0:
                response = requests.get(biblio_glutton_url + "pmc=" + pmcid, verify=False, timeout=5)  
                success = (response.status_code == 200)
                if success:
                    jsonResult = response.json()

            if not success and istex_id is not None and len(istex_id)>0:
                response = requests.get(biblio_glutton_url + "istexid=" + istex_id, verify=False, timeout=5)
                success = (response.status_code == 200)
                if success:
                    jsonResult = response.json()

        if not success and doi is not None and len(doi)>0 and "crossref_base" in self.config and len(self.config["crossref_base"].strip())>0:
            # let's call crossref as fallback for possible X-months gap in biblio-glutton
            # https://api.crossref.org/works/10.1037/0003-066X.59.1.29
            if "crossref_email" in self.config and len(self.config["crossref_email"].strip())>0:
                user_agent = {'User-agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:95.0) Gecko/20100101 Firefox/95.0 (mailto:'+self.config["crossref_email"]+')'}
            else:
                user_agent = {'User-agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:95.0) Gecko/20100101 Firefox/95.0'}
            try:
                logging.info("calling... " + self.config["crossref_base"]+"/works/"+doi)
                response = requests.get(self.config["crossref_base"]+"/works/"+doi, headers=user_agent, verify=False, timeout=5)
                if response.status_code == 200:
                    jsonResult = response.json()['message']
                    # filter out references and re-set doi, in case there are obtained via crossref
                    if "reference" in jsonResult:
                        del jsonResult["reference"]
                else:
                    success = False
                    jsonResult = None
            except:
                logging.exception("Could not connect to CrossRef")
        
        return jsonResult

def generateStoragePath(identifier):
    '''
    Convert a file name into a path with file prefix as directory paths:
    123456789 -> 12/34/56/123456789
    '''
    return os.path.join(identifier[:2], identifier[2:4], identifier[4:6], identifier[6:8], "")

def _deserialize_pickle(serialized):
    return pickle.loads(serialized)

def _clean_json(d):
    # clean recursively a json for insertion in MongoDB, basically remove keys starting with $
    if not isinstance(d, (dict, list)):
        return d
    if isinstance(d, list):
        return [_clean_json(v) for v in d]
    return {k: _clean_json(v) for k, v in d.items()
            if not k.startswith("$") }

BUF_SIZE = 65536    

def getSHA1(the_file):
    sha1 = hashlib.sha1()

    with open(the_file, 'rb') as f:
        while True:
            data = f.read(BUF_SIZE)
            if not data:
                break
            sha1.update(data)

    return sha1.hexdigest()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description = "Softcite software mention recognizer client")
    parser.add_argument("--repo-in", default=None, help="path to a directory of PDF files to be processed by the Softcite software mention recognizer")  
    parser.add_argument("--file-in", default=None, help="a single PDF input file to be processed by the Softcite software mention recognizer") 
    parser.add_argument("--file-out", default=None, help="path to a single output the software mentions in JSON format, extracted from the PDF file-in") 
    parser.add_argument("--data-path", default=None, help="path to the resource files created/harvested by biblio-glutton-harvester") 
    parser.add_argument("--config", default="./config.json", help="path to the config file, default is ./config.json") 
    parser.add_argument("--reprocess", action="store_true", help="reprocessed failed PDF") 
    parser.add_argument("--reset", action="store_true", help="ignore previous processing states and re-init the annotation process from the beginning") 
    parser.add_argument("--load", action="store_true", help="load json files into the MongoDB instance, the --repo-in or --data-path parameter must indicate the path "
        +"to the directory of resulting json files to be loaded, --dump must indicate the path to the json dump file of document metadata") 
    parser.add_argument("--diagnostic", action="store_true", help="perform a full count of annotations and diagnostic using MongoDB "  
        +"regarding the harvesting and transformation process") 
    parser.add_argument("--scorched-earth", action="store_true", help="remove a PDF file after its sucessful processing in order to save storage space" 
        +", careful with this!") 

    args = parser.parse_args()

    data_path = args.data_path
    config_path = args.config
    reprocess = args.reprocess
    reset = args.reset
    file_in = args.file_in
    file_out = args.file_out
    repo_in = args.repo_in
    load_mongo = args.load
    full_diagnostic = args.diagnostic
    scorched_earth = args.scorched_earth

    client = software_mentions_client(config_path=config_path)

    if not load_mongo and not client.service_isalive():
        sys.exit("Softcite software mention service not available, leaving...")

    force = False
    if reset:
        client.reset()
        force = True

    if scorched_earth:
        client.scorched_earth = True

    if load_mongo:
        if data_path is None:
            data_path = client.config["data_path"] 
        # check a mongodb server is specified in the config
        if client.config["mongo_host"] is None:
            sys.exit("the mongodb server where to load the json files is not indicated in the config file, leaving...")
        if repo_in is None and data_path is None: 
            sys.exit("the repo_in where to find the PDF files to be processed is not indicated, leaving...")
        if data_path is not None:
            client.load_mongo(data_path)
        elif repo_in is not None:
            client.load_mongo(repo_in)
    elif full_diagnostic:
        client.diagnostic(full_diagnostic=True)
    elif reprocess:
        client.reprocess_failed()
    elif repo_in is not None: 
        client.annotate_directory(repo_in, force)
    elif file_in is not None:
        client.annotate(file_in, file_out, None)
    elif data_path is not None: 
        client.annotate_collection(data_path, force)

    if not full_diagnostic:
        client.diagnostic(full_diagnostic=False)
    
    
