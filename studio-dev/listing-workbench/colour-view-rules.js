// Presentation predicates only. These do not authorize generation or export.
const ColourViewRules={
 confirmedMasters(groups){return groups.filter(row=>row.listingEligible!==false&&row.ready)},
 targets(groups,masterKey){return groups.filter(row=>row.key!==masterKey)},
 canGenerate(group,active,reference,masterKey){return !active&&!!group?.ready&&!!reference&&!!masterKey},
 canGenerateAll(groups,active,masterKey){return !active&&!!masterKey&&groups.some(row=>row.ready&&row.key!==masterKey)}
};
