# Softcite software mention recognizer client

[![PyPI version](https://badge.fury.io/py/software_mentions_client.svg)](https://badge.fury.io/py/software_mentions_client)
[![License](http://img.shields.io/:license-apache-blue.svg)](http://www.apache.org/licenses/LICENSE-2.0.html)

Python client for using the Softcite software mention recognition service. It can be applied to 

* individual PDF or XML fulltext file

* recursively to a local directory, processing all the encountered PDF and XML fulltext files

* to a collection of documents harvested by [biblio-glutton-harvester](https://github.com/kermitt2/biblio-glutton-harvester) and [article-dataset-builder](https://github.com/kermitt2/article-dataset-builder), with the benefit of re-using the collection manifest for injectng metadata and keeping track of progress. The collection can be stored locally or on a S3 storage. 

## Requirements

The client has been tested with Python 3.5-3.8. 

The client requires a working [Softcite software mention recognition service](https://github.com/ourresearch/software-mentions). Service host and port can be changed in the `config.json` file of the client. 

## Install

```console
> git clone https://github.com/softcite/software_mentions_client.git
> cd software_mentions_client/
```

It is advised to setup first a virtual environment to avoid falling into one of these gloomy python dependency marshlands:

```console
> virtualenv --system-site-packages -p python3 env
> source env/bin/activate
```

Install the dependencies, use:

```console
> python3 -m pip install -r requirements.txt
```

Finally install the project in editable state

```console
> python3 -m pip install -e .
```


## Usage and options

```
usage: python3 -m software_mentions_client.client [-h] [--repo-in REPO_IN] [--file-in FILE_IN] [--file-out FILE_OUT]
                 [--config CONFIG] [--reprocess] [--reset] [--load]
                 [--diagnostic-mongo] [--diagnostic-files] [--scorched-earth]

Softcite software mention recognizer client

optional arguments:
  -h, --help            show this help message and exit
  --repo-in REPO_IN     path to a directory of PDF or XML fulltext files to be processed by the
                        Softcite software mention recognizer
  --file-in FILE_IN     a single PDF or XML input file to be processed by the Softcite software
                        mention recognizer
  --file-out FILE_OUT   path to a single output the software mentions in JSON format, extracted
                        from the PDF file-in
  --config CONFIG       path to the config file, default is ./config.json
  --reprocess           reprocessed failed PDF or XML fulltexts
  --reset               ignore previous processing states and re-init the annotation process
                        from the beginning
  --load                load json files into the MongoDB instance, the --repo-in or --data-path
                        parameter must indicate the path to the directory of resulting json
                        files to be loaded, --dump must indicate the path to the json dump file
                        of document metadata
  --diagnostic-mongo    perform a full count of annotations and diagnostic using MongoDB
                        regarding the harvesting and annotation process
  --diagnostic-files    perform a full count of annotations and diagnostic using repository
                        files regarding the harvesting and annotation process
  --scorched-earth      remove the PDF or XML fulltext files file after their sucessful
                        processing in order to save storage space, careful with this!
```

The logs are written by default in a file `./client.log`, but the location of the logs can be changed in the configuration file (default `./config.json`).

## Processing local PDF files

### Processing a single file

For processing a single file, the resulting json being written as file at the indicated output path:

```console
python3 -m software_mentions_client.client --file-in toto.pdf --file-out toto.json
```

The default config file is `./config.json`, but could also be specified via the parameter `--config`: 

```console
python3 -m software_mentions_client.client --file-in toto.pdf --file-out toto.json --config ./my_config.json
```

### Processing recursively a directory of PDF and XML files

For processing recursively a directory of PDF files, the results will be:

* written to a mongodb server and database indicated in the config file

* *and* in the directory of PDF files, as json files, together with each processed PDF

```console
python3 -m software_mentions_client.client --repo-in /mnt/data/biblio/pmc_oa_dir/
```

The default config file is `./config.json`, but could also be specified via the parameter `--config`: 

```console
python3 -m software_mentions_client.client --repo-in /mnt/data/biblio/pmc_oa_dir/ --config ./my_config.json
```

If, for any reason, the process is stopped, it can be resumed by entering the exact same command: 

```console
python3 -m software_mentions_client.client --repo-in /mnt/data/biblio/pmc_oa_dir/
```

This will continue the processing of the input PDF and XML files not yet processed. 

Anntations will be added along the PDF and XML files, with extension `*.software.json`, e.g.:

```
-rw-rw-r-- 1 lopez lopez 1.1M Aug  8 03:26 0100a44b-6f3f-4cf7-86f9-8ef5e8401567.pdf
-rw-rw-r-- 1 lopez lopez  485 Aug  8 03:41 0100a44b-6f3f-4cf7-86f9-8ef5e8401567.software.json
```

### Reprocess failed PDF or XML fulltexts

Just add `--reprocess` to the command line, the processing will be limited to the PDF and XML files that failed when processing them: 

```console
python3 -m software_mentions_client.client --repo-in /mnt/data/biblio/pmc_oa_dir/ --reprocess
```

## Loading annotation files into MongoDB

Using `--load` option will trigger the loading of all the produced annotations into a MongoDB server indicated in the configuration file. 

```console
python3 -m software_mentions_client.client --load 
```

## Getting a diagnostic and statistics about the processing

After the processing of a repository of PDF and XML files, it is possible to get detailed statistics about the produced annotations. 

The `--diagnostic-files` option performs a full count of annotations and diagnostic using repository files regarding the existing file and the annotation process. 

```console
python3 -m software_mentions_client.client --diagnostic-file 
```

The `--diagnostic-mongo` option performs a full count of annotations and diagnostic using MongoDB regarding the existing files and the annotation process. It supposes that the annotations have been loaded into a MongoDB instance, but it is faster and more complete than the `--diagnostic-files` option. 

```console
python3 -m software_mentions_client.client --diagnostic-mongo 
```

## Configuration

By default, the concurreny of the parallelized calls to a service is `8`. This parameter can be changed in the configuration file `config.json`.

Other important configuration parameter are the URL of the Software mention recognition web service `software_mention_url`, the MongoDb instance information if you wish to load the produced annotations in MongoDB.

Normally, the configuration parameters `sleep_time`, `timeout` and `batch_size` do not need to be modified to ensure a robust processing. 

## License and contact

Distributed under [Apache 2.0 license](http://www.apache.org/licenses/LICENSE-2.0). The dependencies used in the project are either themselves also distributed under Apache 2.0 license or distributed under a compatible license. 

If you contribute to Softcite software mention recognizer client project, you agree to share your contribution following these licenses. 

Main author and contact: Patrice Lopez (<patrice.lopez@science-miner.com>)
