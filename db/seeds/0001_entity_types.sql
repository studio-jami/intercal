-- 0001_entity_types.sql
-- Seed the stable entity type vocabulary.
-- ON CONFLICT DO NOTHING makes this idempotent.

INSERT INTO entity_types (id, label, description) VALUES
    ('person',              'Person',              'A human individual — historical, public, or private.'),
    ('organization',        'Organization',        'A company, institution, government body, non-profit, or other collective.'),
    ('place',               'Place',               'A geographic location: city, country, region, building, etc.'),
    ('role',                'Role',                'A named position or function, e.g. "CEO of OpenAI". Not an alias for the holder.'),
    ('office',              'Office',              'A formal institutional office, e.g. "US Secretary of State". Not an alias for the current occupant.'),
    ('product',             'Product',             'A software product, hardware device, service, or physical good.'),
    ('event',               'Event',               'A discrete occurrence with a time and often a place: conference, election, acquisition, etc.'),
    ('concept',             'Concept',             'An abstract idea, field, technology, or methodology.'),
    ('legislation',         'Legislation',         'A law, regulation, treaty, directive, or bill.'),
    ('technical_artifact',  'Technical Artifact',  'A specific version of a codebase, model, dataset, specification, or standards document.'),
    ('source',              'Source',              'A data origin modeled as an entity (e.g. a news publication, research institution).'),
    ('dataset',             'Dataset',             'A named, structured collection of data (e.g. a benchmark, registry dump).'),
    ('jurisdiction',        'Jurisdiction',        'A legal or regulatory territory: a country, state, or supranational body with authority.')
ON CONFLICT (id) DO NOTHING;
