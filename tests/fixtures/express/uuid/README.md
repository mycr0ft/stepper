# uuid identity schema fixtures — provenance

From the official SMRL v12 zip
(https://standards.iso.org/iso/10303/smrl/v12/tech/smrlv12.zip,
Last-Modified 2025-10-08, full tree git-inited at
~/proj/third_party/smrlv12):

- `uuid_attribute_schema.exp` — the support resource (ISO 10303-41
  ed8 derivative, WG12 N11569): the normative identity-carrier
  schema. Carries ISO's royalty-free license text: "Permission is
  hereby granted, free of charge in perpetuity, ... to use, copy,
  modify, merge and distribute free of charge".

- `universally_unique_identification_assignment_{arm,mim}.exp` —
  ISO/TS 10303-1028 (N11523/N11524), NEW in v12: binds uuid-bearing
  items into the MIM.

- `reference_schema_for_sysml_mapping_v12_concatenated.exp` — the
  full -239+-442+-400 concatenation (v12, 2,446+ entities), carrying
  the Uuid_* family (Uuid_attribute abstract supertype with
  V4/V5 + Hash_based_v5_uuid_attribute + approximate-location,
  Uuid_context, Uuid_relationship, Uuid_provenance).

Phase C significance: the standard now defines content-addressed
instance identity (Hash_based_v5_uuid_attribute: uuid + hash_function
+ identified_item) — the counterpart of sysmlpy's stable-id
interchange ids. The Vee join can map Uuid_relationship onto the
pyoslc link table (uuid_1 = SysML @id, uuid_2 = STEP instance uuid,
role = realizes|specifies|traces).
