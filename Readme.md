# Softcite software mention recognizer client

Python client for using the Softcite software mention recognition service. It can be applied to 

* individual PDF files

* recursively to a local directory, processing all the encountered PDF 

* to a collection of documents harvested by [biblio-glutton-harvester](https://github.com/kermitt2/biblio-glutton-harvester) and [article-dataset-builder](https://github.com/kermitt2/article-dataset-builder), with the benefit of re-using the collection manifest for injectng metadata and keeping track of progress. The collection can be stored locally or on a S3 storage. 


## Requirements

The client has been tested with Python 3.5-3.7. 

The client requires a working [Softcite software mention recognition service](https://github.com/ourresearch/software-mentions). Service host and port can be changed in the `config.json` file of the client. 

## Install

```console
> git clone https://github.com/softcite/software_mentions_client.git
> cd software_mentions_client/
```

It is advised to setup first a virtual environment to avoid falling into one of these gloomy python dependency marshlands:

```console
> virtualenv --system-site-packages -p python3 env
```

```console
> source env/bin/activate
```

Install the dependencies, use:

```console
> pip3 install -r requirements.txt
```

Finally install the project in editable state

```console
> pip3 install -e .
```


## Usage and options

```
usage: software_mentions_client/client.py [-h] [--repo-in REPO_IN] [--file-in FILE_IN]
                                  [--file-out FILE_OUT]
                                  [--data-path DATA_PATH] [--config CONFIG]
                                  [--reprocess] [--reset] [--load]
                                  [--diagnostic] [--scorched-earth]

Softcite software mention recognizer client

optional arguments:
  -h, --help            show this help message and exit
  --repo-in REPO_IN     path to a directory of PDF files to be processed by
                        the Softcite software mention recognizer
  --file-in FILE_IN     a single PDF input file to be processed by the
                        Softcite software mention recognizer
  --file-out FILE_OUT   path to a single output the software mentions in JSON
                        format, extracted from the PDF file-in
  --data-path DATA_PATH
                        path to the resource files created/harvested by
                        biblio-glutton-harvester
  --config CONFIG       path to the config file, default is ./config.json
  --reprocess           reprocessed failed PDF
  --reset               ignore previous processing states and re-init the
                        annotation process from the beginning
  --load                load json files into the MongoDB instance, the --repo-
                        in parameter must indicate the path to the directory
                        of resulting json files to be loaded
  --diagnostic          perform a full count of annotations and diagnostic
                        using MongoDB regarding the harvesting and
                        transformation process
  --scorched-earth      remove a PDF file after its successful processing in
                        order to save storage space, careful with this!
```

The logs are written by default in a file `./client.log`, but the location of the logs can be changed in the configuration file (default `./config.json`).

### Processing local PDF files

For processing a single file., the resulting json being written as file at the indicated output path:

> python3 software_mentions_client/client.py --file-in toto.pdf --file-out toto.json

For processing recursively a directory of PDF files, the results will be:

* written to a mongodb server and database indicated in the config file

* *and* in the directory of PDF files, as json files, together with each processed PDF

> python3 software_mentions_client/client.py --repo-in /mnt/data/biblio/pmc_oa_dir/

The default config file is `./config.json`, but could also be specified via the parameter `--config`: 

> python3 software_mentions_client/client.py --repo-in /mnt/data/biblio/pmc_oa_dir/ --config ./my_config.json


### Processing a collection of PDF harvested by biblio-glutton-harvester

[biblio-glutton-harvester](https://github.com/kermitt2/biblio-glutton-harvester) and [article-dataset-builder](https://github.com/kermitt2/article-dataset-builder) creates a collection manifest as a LMDB database to keep track of the harvesting of large collection of files. Storage of the resource can be located on a local file system or on a AWS S3 storage. The `software-mention` client will use the collection manifest to process these harvested documents. 

* locally:

> python3 software_mentions_client/client.py --data-path /mnt/data/biblio-glutton-harvester/data/

`--data-path` indicates the path to the repository of data harvested by [biblio-glutton-harvester](https://github.com/kermitt2/biblio-glutton-harvester).

The resulting JSON files will be enriched by the metadata records of the processed PDF and will be stored together with each processed PDF in the data repository. 

If the harvested collection is located on a S3 storage, the access information must be indicated in the configuration file of the client `config.json`. The extracted software mention will be written in a file with extension `.software.json`, for example:

```
-rw-rw-r-- 1 lopez lopez 1.1M Aug  8 03:26 0100a44b-6f3f-4cf7-86f9-8ef5e8401567.pdf
-rw-rw-r-- 1 lopez lopez  485 Aug  8 03:41 0100a44b-6f3f-4cf7-86f9-8ef5e8401567.software.json
```

If a MongoDB server access information is indicated in the configuration file `config.json`, the extracted information will additionally be written in MongoDB. 

## License and contact

Distributed under [Apache 2.0 license](http://www.apache.org/licenses/LICENSE-2.0). The dependencies used in the project are either themselves also distributed under Apache 2.0 license or distributed under a compatible license. 

Main author and contact: Patrice Lopez (<patrice.lopez@science-miner.com>)
