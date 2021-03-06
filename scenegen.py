#!/usr/bin/env python3

import sys
import operator
import argparse
import configparser
from urllib import parse

import requests
import yaml

__version__ = '0.0.1'

LIGHT_ATTRS = ['transition', 'profile', 'brightness', 'flash']
LIGHT_COLOR_TYPES = ['xy_color', 'rgb_color', 'color_name', 'color_temp']


def error(message):
    """Output an error and exit"""
    sys.stderr.write("error: %s\n" % message)
    sys.exit(1)

def get_states(url, key=None, ssl_verify=None):
    """Get a dump of all current entities in Home Assistant"""
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'scenegen {}'.format(__version__),
    }
    if key:
        headers['Authorization'] = "Bearer {}".format(key)
        headers['X-HA-Access'] = key

    apiurl = parse.urljoin(url, '/api/states')
    resp = requests.get(apiurl, headers=headers, verify=ssl_verify)

    if resp.status_code != 200:
        error("Error calling Home Assistant: {}, {}".format(resp.status_code, resp.reason))

    states = resp.json()
    # Sort to make output more consistent
    states.sort(key=operator.itemgetter('entity_id'))
    return states

def output_attrs(state, args):
    """Filter an entity attributes for use with a Home Assistant scene"""
    device_type = state['entity_id'].split('.')[0]
    nustate = {}

    # Light
    if device_type in args.types:
        if device_type == 'light':
            nustate['state'] = state['state']
            # Copy required attributes
            for attr in LIGHT_ATTRS:
                if attr in state['attributes']:
                    nustate[attr] = state['attributes'][attr]
            # Add in color type state if set
            if args.colortype and args.colortype in state['attributes']:
                nustate[args.colortype] = state['attributes'][args.colortype]
            else:
                # If the requested color type isn't available, output the first one we can find
                for attr in LIGHT_COLOR_TYPES:
                    if attr in state['attributes']:
                        nustate[attr] = state['attributes'][attr]
                        break
        # Switch
        elif device_type == 'switch':
            nustate = state['state']
        else:
            error('Unsupported device type ({}) detected while trying to process entity {}'.format(device_type, state['entity_id']))
        return {state['entity_id']: nustate}
    return None


def list_scenes(args=None):
    """
    Return the entity IDs for all scenes available to Home Assistant.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'url', metavar='URL', help='The URL for Home Assistant instance')
    parser.add_argument(
        '-t', '--token', metavar='TOKEN',
        help='A long lasting access token to authenticate to the REST API.')

    args = parser.parse_args(args)

    # Filter scenes first to sort on the smaller set
    started_scenes = False
    for state in get_states(args.url, args.token):
        if not state['entity_id'].startswith('scene.'):
            # The states are already sorted so no need to continue past the
            # last scene
            if started_scenes:
                break
            else:
                continue
        started_scenes = True

        entity_id = state['entity_id'].split('.', 1)[1]
        print(entity_id)


def main():
    # Get command line args
    parser = argparse.ArgumentParser()

    parser.add_argument('url', help='url for Home Assistant instance')
    parser.add_argument('-k', '--key', help='API Key of Home Assistant instance')
    parser.add_argument('-s', '--scenename', help='Name of scene to generate', default='My New Scene')
    parser.add_argument('-m', '--mapfile', help='Name of mapfile to enable device filtering')
    parser.add_argument('-f', '--filter', help='Comma separated list of device collections as defined in mapfile')
    parser.add_argument('-c', '--colortype', help='color type to use', default='xy_color', choices=LIGHT_COLOR_TYPES)
    parser.add_argument('-t', '--types', help='list of device types to include', default='light,switch')
    parser.add_argument('--no-sslverify', help='disables SSL verification, useful for self signed certificates', action='store_true')
    parser.add_argument('--cacerts', help='alternative set of trusted CA certificates to use for connecting to Home Assistant')
    args = parser.parse_args()

    filter_list = []
    if args.mapfile and args.filter:
        filters = args.filter.split(',')

        # Load in the mapfile, any sections that match a filter, load the option keys into the filter list
        config = configparser.ConfigParser()
        with open(args.mapfile, 'r') as fobj:
            config.read_file(fobj)
        for section in config.sections():
            if section in filters:
                filter_list.extend(config.options(section))

    # Check if to disable SSL verification, or provide alternative CA certs
    ssl_verify = None
    if args.no_sslverify:
        ssl_verify = False
    elif args.cacerts:
        ssl_verify = args.cacerts

    try:
        states = get_states(args.url, args.key, ssl_verify)
    except requests.exceptions.RequestException as exc:
        error('Unknown error occured while trying to read the state from Home Assistant: {}'.format(str(exc)))

    # Iterate all entities and produce a scene
    output = {'entities': {}, 'name': args.scenename}
    for state in states:
        if args.mapfile and args.filter:
            # If we're provided with a map file and filter list, exclude the match entities
            if state['entity_id'] not in filter_list:
                continue
        entity_state = output_attrs(state, args)
        if entity_state:
            output['entities'].update(entity_state)

    # Write the resulting YAML to stdout
    sys.stdout.write(yaml.dump(output, default_flow_style=False))

if __name__ == '__main__':
    main()
