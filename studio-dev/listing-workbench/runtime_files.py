"""Files needed by the ERP adapters in source and portable installations."""
MODULES = (
    'atomic_write_json.mjs', 'ego-collection-inbox.mjs', 'ego-collection-lookup.mjs',
    'ego-collection-prepare.mjs', 'ego-collection-upload.mjs', 'ego-collection-workflow.mjs',
    'ego-copy-native.mjs', 'ego-draft-images.mjs', 'ego-draft-readback.mjs',
    'ego-draft-save.mjs', 'ego-existing-draft.mjs', 'ego-explicit-galleries.mjs',
    'ego-finished-collection.mjs', 'ego-library-draft.mjs', 'ego-library-images.mjs',
    'ego-library-package.mjs', 'ego-native-transfer.mjs', 'ego-publication-identifiers.mjs',
    'ego-publication-main-image.mjs', 'ego-publication-media-episode.mjs', 'ego-publication-recovery.mjs',
    'ego-publication-required-attributes.mjs', 'ego-publication-uk-media.mjs', 'ego-publication-workflow.mjs',
    'ego-publish-native.mjs', 'ego-schema-validator.mjs', 'ego-uk-draft.mjs',
    'ego-uk-exemption.mjs', 'ego-us-draft.mjs', 'existing-draft.mjs',
    'listing.mjs', 'validate_attributes.py',
)
AUTOMATION_TOOLS = ('ego_browser.py','ziniao_plugin.py','ziniao_market.py')
REQUIRED_FILES = ('junfei-publisher/ego_link.py', *(f'automation/{name}' for name in AUTOMATION_TOOLS),
                  *(f'junfei-publisher/{name}' for name in MODULES))
