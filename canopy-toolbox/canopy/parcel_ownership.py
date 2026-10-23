"""Explicit public-owner aliases; tax exemption alone never means government."""
import re


def normalize(owner):
    return ' '.join(re.sub(r'[^A-Z0-9&;]', ' ', str(owner or '').upper()).split())


PUBLIC_ALIASES = {
    normalize(name): group for group, names in {
        'MILLCREEK': ['MILLCREEK', 'MILLCREEK CITY', 'CITY OF MILLCREEK', 'A UTAH MUNICIPALITY MILLCREEK'],
        'SALT_LAKE_COUNTY': ['SALT LAKE COUNTY', 'COUNTY OF SALT LAKE', 'SALT LAKE COUNTY REAL ESTATE',
                             'SALT LAKE COUNTY FLOOD CONTROL'],
        'SALT_LAKE_CITY': ['SALT LAKE CITY', 'SALT LAKE CITY CORP.', 'SALT LAKE CITY CORPORATION'],
        'STATE_OF_UTAH': ['STATE OF UTAH', 'UTAH DEPARTMENT OF TRANSPORTATION', 'STATE ROAD COMMISSION',
                          'STATE ROAD COMMISSION OF UTAH', 'UTAH STATE BUILDING OWNERSHIP AUTHORITY',
                          'UTAH SCHOOLS FOR THE DEAF AND THE BLIND',
                          'STATE OF UTAH DIVISION OF FACILITIES CONSTRUCTION',
                          'STATE OF UTAH; STATE OF UTAH, UTAH STATE BOARD OF EDUCATION SCHOOL; FOR THE DEAF AND BLIND'],
        'FEDERAL': ['UNITED STATES OF AMERICA'],
        'PUBLIC_DISTRICT': ['UTAH TRANSIT AUTHORITY', 'TAYLORSVILLE-BENNION IMPROVEMENT DISTRICT',
                            'MT OLYMPUS IMPROVEMENT DISTRICT',
                            'METROPOLITAN WATER DISTRICT OF SALT LAKE & SANDY', 'METROPOLITAN WATER DISTRICT',
                            'SALT LAKE COUNTY WATER CONSERVANCY DISTRICT',
                            'LOCAL BLDG AUTHORITY OF SALT LAKE VALLEY FIRE SERVICE AREA',
                            'LOCAL BLDG AUTHORITY OF SL VALLEY FIRE SERVICE AREA UTAH'],
        'PUBLIC_HOUSING': ['HOUSING AUTHORITY OF THE COUNTY OF SALT LAKE',
                           'THE HOUSING AUTHORITY OF THE COUNTY OF SALT LAKE'],
        'PUBLIC_SCHOOL': ['GRANITE SCHOOL DISTRICT', 'THE GRANITE SCHOOL DISTRICT',
                          'GRANITE SCHOOL BOARD OF EDUCATION', 'GRANITE SCHOOL DISTRICT BOARD OF EDUCATION',
                          'BOARD OF EDUCATION OF THE GRANITE SCHOOL DIST',
                          'BOARD OF EDUCATION OF GRANITE SCHOOL DIST.',
                          'BOARD OF EDUCATION OF GRANITE SCHOOL DISTRICT',
                          'BOARD OF EDUCATION OF THE GRANITE SCHOOL DISTRICT',
                          'THE BOARD OF EDUCATION OF GRANITE SCHOOL DISTRICT',
                          'BOARD OF EDUCATION OF GRANITE SCHOOL DIST',
                          'BOARD OF EDUCATIO OF GRANITE SCHOOL DISTRICT, THE',
                          'BOARD OF EDUCATION OF THE GRANITE DISTRICT',
                          'THE BOARD OF EDUCATION OF THE GRANITE SCHOOL DISTRICT',
                          'BOARD OF EDUCATION GRANITE SCHOOL DISTRICT'],
    }.items() for name in names
}


def classify(owner):
    name = normalize(owner)
    if not name:
        return 'UNKNOWN_OWNER', 'Missing owner of record'
    if name in PUBLIC_ALIASES:
        return 'PUBLIC_GOVERNMENT', PUBLIC_ALIASES[name]
    # Preserve ambiguous, truncated and mixed government ownership for review.
    if (name.startswith('LAKE COUNTY TITLE BY') or name == 'SALT LAKE CITY PROPERTY MANAGEMENT' or
            any(public in name for public in ['SALT LAKE COUNTY;', 'STATE OF UTAH;',
                                              'COUNTY OF SALT LAKE;', 'UNITED STATES OF AMERICA;'])):
        return 'UNKNOWN_OWNER', 'Ambiguous or mixed government owner'
    return 'PRIVATE', 'Other named owner; includes private utilities, churches and nonprofits'


def resolve(categories):
    values = set(categories)
    if not values:
        return 'NO_PARCEL'
    if len(values) == 1:
        return next(iter(values))
    return 'OWNERSHIP_CONFLICT'
