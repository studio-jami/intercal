-- 0002_relationship_types.sql
-- Seed the stable relationship type vocabulary.
-- ON CONFLICT DO NOTHING makes this idempotent.
-- is_exclusive = true means at most one active interval should exist per (subject, object) pair;
-- enforced at application layer; stored here as declarative intent.

INSERT INTO relationship_types (id, label, description, is_directional, is_exclusive) VALUES

    -- Role / office occupancy
    ('person_holds_role',
        'Person Holds Role',
        'A person occupies a named role (e.g. CEO of OpenAI). Temporal: valid_from/valid_until model term of office.',
        true, true),

    ('person_holds_office',
        'Person Holds Office',
        'A person holds a formal institutional office (e.g. US Secretary of State). Temporal term, exclusive per office.',
        true, true),

    -- Organizational structure
    ('organization_employs_person',
        'Organization Employs Person',
        'An organization has an employment relationship with a person.',
        true, false),

    ('organization_owns_product',
        'Organization Owns Product',
        'An organization owns or maintains a product, service, or technical artifact.',
        true, false),

    ('organization_subsidiary_of',
        'Organization Subsidiary Of',
        'One organization is a subsidiary of another.',
        true, false),

    -- Corporate events
    ('company_acquired_company',
        'Company Acquired Company',
        'One organization acquired another. Subject = acquirer, object = acquired.',
        true, false),

    ('company_merged_with_company',
        'Company Merged With Company',
        'Two organizations merged. Conventionally ordered alphabetically.',
        true, false),

    -- Academic / research
    ('paper_cites_paper',
        'Paper Cites Paper',
        'A source document (paper) cites another.',
        true, false),

    ('person_authored_artifact',
        'Person Authored Artifact',
        'A person authored or co-authored a technical artifact or publication.',
        true, false),

    ('organization_published_artifact',
        'Organization Published Artifact',
        'An organization published or released a technical artifact.',
        true, false),

    -- Legislative / regulatory
    ('law_amends_law',
        'Law Amends Law',
        'One piece of legislation amends or supersedes another.',
        true, false),

    ('jurisdiction_enacted_legislation',
        'Jurisdiction Enacted Legislation',
        'A jurisdiction enacted or enforces a piece of legislation.',
        true, false),

    -- Geographic
    ('event_occurred_in_place',
        'Event Occurred In Place',
        'An event occurred in a geographic location.',
        true, false),

    ('organization_headquartered_in',
        'Organization Headquartered In',
        'An organization is or was headquartered in a place. Temporal.',
        true, true),

    ('person_born_in',
        'Person Born In',
        'A person was born in a place.',
        true, false),

    -- Sourcing / provenance
    ('source_reported_claim',
        'Source Reported Claim',
        'A source document reported or asserted a claim.',
        true, false),

    -- Claim relations
    ('claim_contradicts_claim',
        'Claim Contradicts Claim',
        'Two claims assert incompatible facts about the same subject. Symmetric; order by UUID.',
        false, false),

    ('claim_supports_claim',
        'Claim Supports Claim',
        'One claim provides corroborating evidence for another.',
        true, false),

    -- Concept / topic
    ('entity_instance_of_concept',
        'Entity Instance Of Concept',
        'An entity is an instance or example of a concept.',
        true, false),

    ('concept_related_to_concept',
        'Concept Related To Concept',
        'Two concepts are related. Symmetric; order by UUID.',
        false, false)

ON CONFLICT (id) DO NOTHING;
