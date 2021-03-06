"""This script collects metrics from APEL (Alex T/SCD/2018)"""
import requests
import xml.dom.minidom
from datetime import datetime, timedelta
from elasticsearch import Elasticsearch
import logging
from common import GetData, ModLogger, ESWrite, es_check, gocdb_check
from optparse import OptionParser


ELASTIC_SEARCH_HOST = "elasticsearch2.gridpp.rl.ac.uk"
logger = logging.getLogger('APEL logger')
country_list = []

def get_sites(endpoint, data_obj):
    """
    This function finds the sites using each endpoint.

    Params
    ------
    endpoint: string
              This is the endpoint for which the metrics are collected
    data_obj: xml minidom object
              This is where the data needed for the function is stored

    Returns
    ------
    len(sitename_list): int
                        This is the number of sites using the endpoint
    sitename_list: list
                   This is a list of all the sites using an endpoint
    Notes
    -----
    This function uses the "GetData" class.
    """
    sitename_list = []
    for service_endpoint in data_obj:
        gocdb_portal_url = \
                service_endpoint.getElementsByTagName('GOCDB_PORTAL_URL'
                                                      )[0].firstChild.nodeValue

        sitename = GetData('SITENAME', service_endpoint, gocdb_portal_url)
        sitename = sitename.data_finder()
        if sitename not in sitename_list:  # adds the sitenames to a list
                                           # if they are not already in it
            sitename_list.append(sitename)
        else:
            pass
    return(len(sitename_list), sitename_list)

def get_services(endpoint, data_obj):
    """
    This function finds the usage number of each endpoint.

    Params
    ------
    endpoint: string
              This is the endpoint for which the metrics are collected
    data_obj: xml minidom object
              This is where the data needed for the function is stored
    Returns
    -------
    counter: int
             This is the number of times each endpoint is used
    Notes
    -----
    This fucntion also uses the "GetData" class. The function also logs errors
    when a HOSTDN is missing.
    """
    counter = 0
    for service_endpoint in data_obj:
        gocdb_portal_url = \
             service_endpoint.getElementsByTagName('GOCDB_PORTAL_URL'
                                                  )[0].firstChild.nodeValue

        service_type = GetData('SERVICE_TYPE', service_endpoint,
        gocdb_portal_url)
        service_type = service_type.data_finder()
        try:
            hostdn = service_endpoint.getElementsByTagName('HOSTDN'
                     )[0].firstChild.nodeValue
            if service_type == endpoint:
                counter = counter + 1
            else:
                pass
        except IndexError:
            logger.warning('Index error when requesting HOSTDN from '
                            + gocdb_portal_url)
    return counter

def get_countries(endpoint, data_obj):
    """
    This function finds the countries using each endpoint.

    Params
    ------
    endpoint: string
              This is the endpoint for which the metrics are collected
    data_obj: xml minidom object
              This is where the data needed for the function is stored
    Returns
    -------
    country_list_temp: list
                       This is a list of the countries using an endpoint
    len(country_list_temp): int
                            This is the number of countries using an endpoint
    Notes
    -----
    This function uses the global variable "country_list" in order to be able to
    collect metrics across all APEL endpoint types.
    """
    country_list_temp = []
    global country_list
    for service_endpoint in data_obj:
        gocdb_portal_url = \
                service_endpoint.getElementsByTagName('GOCDB_PORTAL_URL'
                                                      )[0].firstChild.nodeValue
        country = GetData('COUNTRY_NAME', service_endpoint, gocdb_portal_url)
        country = country.data_finder()
        try:
            if country not in country_list:
                country_list.append(country)
            else:
                pass
            if country not in country_list_temp:
                country_list_temp.append(country)
            else:
                pass
        except IndexError:
            logger.error("Index error when requesting country name from" +
                          gocdb_portal_url)


    return(country_list_temp, len(country_list_temp))

def get_records(query_type):
    """
    This function gets the records loaded from each query type in elastic search

    Params
    ------
    query_type: string
                This string holds the query type for which the data
                should be collected
    Returns
    -------
    total: int
           This is the number of queries

    Notes
    -----
    The function has been written to work with ElasticSearch 1.5.
    When the cluster is updated the code may have to be changed,
    to allow it to interact with the new cluster.
    This function also makes use of the Elasticsearch module.
    """
    date = datetime.strftime(datetime.now() - timedelta(1), '%Y.%m.%d')
    elastic = Elasticsearch(ELASTIC_SEARCH_HOST)
    params_dict = {
        "query": {
            "bool": {
                "must": [
                    {"match": {"fields.apel_type": query_type}},
                    {"match": {"fields.process": "loader"}}
                ]
            }
        },
        "size": 0,
        "aggs": {
            "total_number_loaded": {"sum": {"field": "numberloaded"}}
        }
    }

    result = elastic.search(index="logstash-" + date, body=params_dict)

    total = result["aggregations"]["total_number_loaded"]["value"]
    return total

def main(options):
    """
    This is the main function. It calls the rest of the functions
    in this script and runs them in order to generate metrics for APEL.
    These metrics can be stored in ElasticSearch by setting oprions to "True".
    If options is not set to true it just prints the dictionary holding the data
    """
    logger.addHandler(logging.NullHandler())
    ModLogger('APEL.log').logger_mod()

    logger.info('Service has started')
    gocdb_up = gocdb_check()
    es_up = es_check()
    # List of service endpoint types to record metrics about
    endpoint_types = ['gLite-APEL', 'APEL', 'eu.egi.cloud.accounting',
                      'eu.egi.storage.accounting']
    query_type_list = ['storage', 'cloud', 'grid']

    # master dictionary
    apel_metrics_dict = {}
    global country_list
    if gocdb_up == True:
        for endpoint in endpoint_types:
            response = \
            requests.get('https://goc.egi.eu/gocdbpi/public/?method='+
                              'get_service_endpoint&service_type='
                              + endpoint, verify=False)

            data = response.text
            context = xml.dom.minidom.parseString(data)
            service_endpoint_obj = \
                context.getElementsByTagName('SERVICE_ENDPOINT')


            (apel_metrics_dict['Number of sites runnning at least one '
                               + endpoint + " endpoint"],
            apel_metrics_dict['List of sites runnning at least one ' +
                               endpoint + " endpoint"]) = \
                              get_sites(endpoint, service_endpoint_obj)

            apel_metrics_dict['Number of ' + endpoint + ' endpoints'] = \
                              get_services(endpoint, service_endpoint_obj)

            (apel_metrics_dict['List of countries with at least one ' + endpoint
                               + ' endpoint'],
            apel_metrics_dict['Number of countries with at least one '+ endpoint
            + ' endpoint']) = get_countries(endpoint, service_endpoint_obj)

        apel_metrics_dict['Total number of countries using APEL '] = \
            len(country_list)
        apel_metrics_dict['Complete list of countries using APEL '] = \
            country_list
    else:
        print "GOCDB is currently down. No metrics can be collected!"

    if es_up == True:
        for query_type in query_type_list:
            apel_metrics_dict['Number of records loaded for ' + query_type
                              + ' accounting'] = get_records(query_type)
    else:
        print("Elastic Search is currently down." +
              " No data could be read or written!")

    if options.write == "True":
        ESWrite(apel_metrics_dict).write()
    else:
        print apel_metrics_dict
    logger.info('Service has ended')

if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-w", "--write-to-elastic", dest="write",
                      default="False",
                      help="Wether to write result to ElasticSearch or not.")

    (options, args) = parser.parse_args()
    main(options)
