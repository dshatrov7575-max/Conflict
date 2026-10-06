"""Issue #90 / 5601837109: exact immutable typed Zhanaozen installation fixture.

OTHER links are technical applicability bridges, not substantive actor roles.
A3/A4 remain PROPOSAL_FOR_FREEZE; A5 is not owner-approved methodology.
This module carries no assessments, values, experiments or runtime source fallback.
"""
from __future__ import annotations

import json

PROJECT_ID = '3de70d1d-f4cf-535a-95b9-94c0a65e60e3'
MANIFEST_SHA256 = '6f149d681d4413d0e8f5cb61c2ed790cf277a385b900b2db35395794c94391ca'
SYSTEM_ACTOR = 'SYSTEM:ZHANAOZEN_TYPED_MANIFEST_BOOTSTRAP_V1'
SYSTEM_PURPOSE = 'CA-SUITE-I1-G8-PRE-CANONICAL-ZHANAOZEN-MANIFEST-001'
SYSTEM_CONTRACT = 'FOUNDATION_ZHANAOZEN_SYSTEM_PROJECTION_V1'
DEFINITION_CODE = 'DEFINITION-ZHANAOZEN-TYPED-1.0.0'
DEFINITION_ROW_VERSION = '2.0.0'
PUBLICATION_CODE = 'PUBLICATION-ZHANAOZEN-TYPED-1.0.0'
LEGACY_DEFINITION_ID = '16acc6cf-9c1b-5fb2-974f-341517a87fc0'
LEGACY_WORKSPACE_ID = 'cc246821-54a3-52d7-bbc7-8bf2c7e635d2'
LEGACY_MANIFEST_SHA256 = '78e90200ca600e847b1e9c635d043592fff1cf14c5a3c097ed23a0a5ec6b761d'
LEGACY_INITIAL_CODE = 'LEGACY-INITIAL-WORKSPACE-REPAIR-1.0.0'
DEFINITION_ID = '08042667-fae6-5f3a-a248-514b9001e088'
WORKSPACE_ID = 'c6e16836-d003-5e6d-9294-932d25e06e3a'
POS_ID = '532433cb-1452-5354-929a-020679d3972d'
SAL_ID = 'a223a247-d834-52fc-a156-e6acaf58b428'
PROJECTION_OPERATION_ID = 'e03c577a-1e8c-5910-a724-2ea3a0ca12c5'
PROJECTION_RECEIPT_ID = '156cac68-c08c-55c3-b041-fe051779e45b'
LEGACY_INITIAL_RECEIPT_ID = '8168c264-e1ac-575a-8d52-c6bc28c9d961'

SYSTEM_CAPABILITIES = frozenset({"DRAFT_CREATE", "DEFINITION_VALIDATE", "DEFINITION_PUBLISH", "STRUCTURE_MUTATE"})

_MANIFEST_JSON = r'''
{
  "$schema": "https://conflictology.invalid/schemas/project-definition-manifest-1.0.0.schema.json",
  "actor_element_roles": [
    {
      "actor_id": "d31904bd-a9e2-52bc-886d-d959d8e6f86d",
      "code": "ROLE-OTHER-GU-01-PTN-01",
      "element_id": "e4311a29-c1a3-5000-9af8-9603d268c7d1",
      "id": "40e5dfc7-8b76-5739-8e6a-6493a0099d23",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 0,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "d31904bd-a9e2-52bc-886d-d959d8e6f86d",
      "code": "ROLE-OTHER-GU-01-PTN-02",
      "element_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
      "id": "72c82424-75f8-5671-a8d5-42a99c276b12",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 1,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "d31904bd-a9e2-52bc-886d-d959d8e6f86d",
      "code": "ROLE-OTHER-GU-01-PTN-03",
      "element_id": "6e3f62f8-6e0b-5b92-8c7c-b37022610a1d",
      "id": "1e973d7c-f605-58b8-9db0-c505df2e67c9",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 2,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "d31904bd-a9e2-52bc-886d-d959d8e6f86d",
      "code": "ROLE-OTHER-GU-01-PTN-04",
      "element_id": "2fecb360-274b-55da-a7d4-6020a87de286",
      "id": "256afb8d-9067-5a1c-b449-b2ab2c101532",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 3,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "d31904bd-a9e2-52bc-886d-d959d8e6f86d",
      "code": "ROLE-OTHER-GU-01-PTN-05",
      "element_id": "728c8406-ba99-5787-9557-933b5670be7c",
      "id": "4b3ffd2d-6511-5b21-bcfa-e5c5b2a123af",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 4,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "d31904bd-a9e2-52bc-886d-d959d8e6f86d",
      "code": "ROLE-OTHER-GU-01-PTN-06",
      "element_id": "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9",
      "id": "e0aec73e-f274-5af1-a3f1-9e9bd2c498fc",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 5,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "4c215889-7a31-56ae-8a60-cc546c915241",
      "code": "ROLE-OTHER-GU-02-PTN-01",
      "element_id": "e4311a29-c1a3-5000-9af8-9603d268c7d1",
      "id": "4d90697f-51ca-5984-a587-7a2566bca3e6",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 6,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "4c215889-7a31-56ae-8a60-cc546c915241",
      "code": "ROLE-OTHER-GU-02-PTN-02",
      "element_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
      "id": "b10a8d08-01a7-507d-8a2d-9ddb9b9e6649",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 7,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "4c215889-7a31-56ae-8a60-cc546c915241",
      "code": "ROLE-OTHER-GU-02-PTN-03",
      "element_id": "6e3f62f8-6e0b-5b92-8c7c-b37022610a1d",
      "id": "cb460ec1-500b-5162-b451-1c443531408e",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 8,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "4c215889-7a31-56ae-8a60-cc546c915241",
      "code": "ROLE-OTHER-GU-02-PTN-04",
      "element_id": "2fecb360-274b-55da-a7d4-6020a87de286",
      "id": "c7ce39ce-3bba-5d35-b89f-2cf1a761891c",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 9,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "4c215889-7a31-56ae-8a60-cc546c915241",
      "code": "ROLE-OTHER-GU-02-PTN-05",
      "element_id": "728c8406-ba99-5787-9557-933b5670be7c",
      "id": "9b6528b2-3ea0-54a3-9bb7-d0304e324873",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 10,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "4c215889-7a31-56ae-8a60-cc546c915241",
      "code": "ROLE-OTHER-GU-02-PTN-06",
      "element_id": "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9",
      "id": "aa8d038a-02af-5cbd-b5fa-f2dfafd76854",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 11,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "6e5f84f6-8988-5e72-8fbd-bf67d4c8bb45",
      "code": "ROLE-OTHER-GU-03-PTN-01",
      "element_id": "e4311a29-c1a3-5000-9af8-9603d268c7d1",
      "id": "17b64c83-df54-5f0f-bb81-ceaf58cc306f",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 12,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "6e5f84f6-8988-5e72-8fbd-bf67d4c8bb45",
      "code": "ROLE-OTHER-GU-03-PTN-02",
      "element_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
      "id": "4a74d189-341c-5a73-a3c9-4b13dc0ed5b5",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 13,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "6e5f84f6-8988-5e72-8fbd-bf67d4c8bb45",
      "code": "ROLE-OTHER-GU-03-PTN-03",
      "element_id": "6e3f62f8-6e0b-5b92-8c7c-b37022610a1d",
      "id": "53f74005-412c-57b4-a2a4-b230d76b2d3b",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 14,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "6e5f84f6-8988-5e72-8fbd-bf67d4c8bb45",
      "code": "ROLE-OTHER-GU-03-PTN-04",
      "element_id": "2fecb360-274b-55da-a7d4-6020a87de286",
      "id": "bca2320f-53d4-5371-9183-b4e1778a5096",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 15,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "6e5f84f6-8988-5e72-8fbd-bf67d4c8bb45",
      "code": "ROLE-OTHER-GU-03-PTN-05",
      "element_id": "728c8406-ba99-5787-9557-933b5670be7c",
      "id": "6f92fafc-ca56-5035-870f-72fe0062dd04",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 16,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "6e5f84f6-8988-5e72-8fbd-bf67d4c8bb45",
      "code": "ROLE-OTHER-GU-03-PTN-06",
      "element_id": "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9",
      "id": "a6c938b5-c948-53c3-9c88-4eb20502f14a",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 17,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "744feea3-d4d4-5a3c-9d65-394894389e67",
      "code": "ROLE-OTHER-GU-04-PTN-01",
      "element_id": "e4311a29-c1a3-5000-9af8-9603d268c7d1",
      "id": "d729707b-4f73-554a-a0fa-cb9c6abd96b5",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 18,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "744feea3-d4d4-5a3c-9d65-394894389e67",
      "code": "ROLE-OTHER-GU-04-PTN-02",
      "element_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
      "id": "156eecc1-4876-50bf-8beb-8fa0ec8e09f8",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 19,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "744feea3-d4d4-5a3c-9d65-394894389e67",
      "code": "ROLE-OTHER-GU-04-PTN-03",
      "element_id": "6e3f62f8-6e0b-5b92-8c7c-b37022610a1d",
      "id": "591df5ca-7b2e-5c2f-a880-12e95e88d794",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 20,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "744feea3-d4d4-5a3c-9d65-394894389e67",
      "code": "ROLE-OTHER-GU-04-PTN-04",
      "element_id": "2fecb360-274b-55da-a7d4-6020a87de286",
      "id": "ade9036e-50af-5add-866d-c096f365d9fd",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 21,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "744feea3-d4d4-5a3c-9d65-394894389e67",
      "code": "ROLE-OTHER-GU-04-PTN-05",
      "element_id": "728c8406-ba99-5787-9557-933b5670be7c",
      "id": "8f84cdb7-1f96-5827-a867-8f96825dc2c3",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 22,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "744feea3-d4d4-5a3c-9d65-394894389e67",
      "code": "ROLE-OTHER-GU-04-PTN-06",
      "element_id": "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9",
      "id": "446a5c74-f0a0-5cec-a795-c26d5da32d60",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 23,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "d803888d-ec24-5c7e-905b-96f88d01c36f",
      "code": "ROLE-OTHER-GU-05-PTN-01",
      "element_id": "e4311a29-c1a3-5000-9af8-9603d268c7d1",
      "id": "e2df521c-538c-5a36-a9f3-7384e1d39644",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 24,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "d803888d-ec24-5c7e-905b-96f88d01c36f",
      "code": "ROLE-OTHER-GU-05-PTN-02",
      "element_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
      "id": "ce41ce1b-3bdb-54bd-8b17-b27224f40c95",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 25,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "d803888d-ec24-5c7e-905b-96f88d01c36f",
      "code": "ROLE-OTHER-GU-05-PTN-03",
      "element_id": "6e3f62f8-6e0b-5b92-8c7c-b37022610a1d",
      "id": "0c8423ba-07d4-597c-ae82-e64e2caa6336",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 26,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "d803888d-ec24-5c7e-905b-96f88d01c36f",
      "code": "ROLE-OTHER-GU-05-PTN-04",
      "element_id": "2fecb360-274b-55da-a7d4-6020a87de286",
      "id": "56fa106e-7397-53f0-adc6-5d2bd5181588",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 27,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "d803888d-ec24-5c7e-905b-96f88d01c36f",
      "code": "ROLE-OTHER-GU-05-PTN-05",
      "element_id": "728c8406-ba99-5787-9557-933b5670be7c",
      "id": "a1423d44-63bf-5c1f-8260-2c2d8b40831d",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 28,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "d803888d-ec24-5c7e-905b-96f88d01c36f",
      "code": "ROLE-OTHER-GU-05-PTN-06",
      "element_id": "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9",
      "id": "de3f65fb-2854-58a3-9916-4b69dbbd92a1",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 29,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "73e1643f-34d5-537d-8f78-bdf15c3b7c35",
      "code": "ROLE-OTHER-GU-06-PTN-01",
      "element_id": "e4311a29-c1a3-5000-9af8-9603d268c7d1",
      "id": "f0935f81-8d39-5c89-8c58-8f578adf753f",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 30,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "73e1643f-34d5-537d-8f78-bdf15c3b7c35",
      "code": "ROLE-OTHER-GU-06-PTN-02",
      "element_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
      "id": "475213b5-e6cb-5c56-8d73-2f20ca3aad6b",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 31,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "73e1643f-34d5-537d-8f78-bdf15c3b7c35",
      "code": "ROLE-OTHER-GU-06-PTN-03",
      "element_id": "6e3f62f8-6e0b-5b92-8c7c-b37022610a1d",
      "id": "c3f93424-c2ae-507d-98ae-b83964164bc6",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 32,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "73e1643f-34d5-537d-8f78-bdf15c3b7c35",
      "code": "ROLE-OTHER-GU-06-PTN-04",
      "element_id": "2fecb360-274b-55da-a7d4-6020a87de286",
      "id": "3601f1ae-8422-50ad-ba34-8961fc891211",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 33,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "73e1643f-34d5-537d-8f78-bdf15c3b7c35",
      "code": "ROLE-OTHER-GU-06-PTN-05",
      "element_id": "728c8406-ba99-5787-9557-933b5670be7c",
      "id": "12f46b6d-2600-56b6-811f-78ba077f16b7",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 34,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "73e1643f-34d5-537d-8f78-bdf15c3b7c35",
      "code": "ROLE-OTHER-GU-06-PTN-06",
      "element_id": "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9",
      "id": "312a43a5-3ca7-51a3-ba63-e35c8440b1a1",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 35,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "fd80f79b-7c39-58db-b122-7245b77ff0c5",
      "code": "ROLE-OTHER-GU-07-PTN-01",
      "element_id": "e4311a29-c1a3-5000-9af8-9603d268c7d1",
      "id": "425cb4cf-20fd-5b32-8cf4-046bc56b2727",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 36,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "fd80f79b-7c39-58db-b122-7245b77ff0c5",
      "code": "ROLE-OTHER-GU-07-PTN-02",
      "element_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
      "id": "d482ea59-37a7-5841-92cf-f576f187f474",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 37,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "fd80f79b-7c39-58db-b122-7245b77ff0c5",
      "code": "ROLE-OTHER-GU-07-PTN-03",
      "element_id": "6e3f62f8-6e0b-5b92-8c7c-b37022610a1d",
      "id": "85bcda97-f661-594d-a926-6ef3c816e7f8",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 38,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "fd80f79b-7c39-58db-b122-7245b77ff0c5",
      "code": "ROLE-OTHER-GU-07-PTN-04",
      "element_id": "2fecb360-274b-55da-a7d4-6020a87de286",
      "id": "9359e149-e276-5fb6-aa94-cf7f6f1379e9",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 39,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "fd80f79b-7c39-58db-b122-7245b77ff0c5",
      "code": "ROLE-OTHER-GU-07-PTN-05",
      "element_id": "728c8406-ba99-5787-9557-933b5670be7c",
      "id": "b1ae2d3d-e2ac-5e1f-8a9b-0a2741f6bafd",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 40,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "fd80f79b-7c39-58db-b122-7245b77ff0c5",
      "code": "ROLE-OTHER-GU-07-PTN-06",
      "element_id": "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9",
      "id": "1aef4911-d213-5bca-9458-43eac819391a",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 41,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "6782018f-1868-5aa7-b40e-fb5ad11269ca",
      "code": "ROLE-OTHER-GU-08-PTN-01",
      "element_id": "e4311a29-c1a3-5000-9af8-9603d268c7d1",
      "id": "a9a8064e-eedd-5c90-813f-09eb1842b0fb",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 42,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "6782018f-1868-5aa7-b40e-fb5ad11269ca",
      "code": "ROLE-OTHER-GU-08-PTN-02",
      "element_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
      "id": "713d1cd0-57c5-5436-ada3-830bcb21d96a",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 43,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "6782018f-1868-5aa7-b40e-fb5ad11269ca",
      "code": "ROLE-OTHER-GU-08-PTN-03",
      "element_id": "6e3f62f8-6e0b-5b92-8c7c-b37022610a1d",
      "id": "f9237dcf-877d-543c-a2d7-b0e980815be9",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 44,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "6782018f-1868-5aa7-b40e-fb5ad11269ca",
      "code": "ROLE-OTHER-GU-08-PTN-04",
      "element_id": "2fecb360-274b-55da-a7d4-6020a87de286",
      "id": "ce11c754-dac0-5666-bd87-32eaa25d3615",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 45,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "6782018f-1868-5aa7-b40e-fb5ad11269ca",
      "code": "ROLE-OTHER-GU-08-PTN-05",
      "element_id": "728c8406-ba99-5787-9557-933b5670be7c",
      "id": "29c24ed9-ad6d-5d3b-87d5-08e218a90b23",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 46,
      "role": "OTHER",
      "version": "1.0.0"
    },
    {
      "actor_id": "6782018f-1868-5aa7-b40e-fb5ad11269ca",
      "code": "ROLE-OTHER-GU-08-PTN-06",
      "element_id": "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9",
      "id": "ff48151f-9a5d-5798-96a8-6595fdce6291",
      "note": "Technical applicability bridge only; no substantive actor-role classification.",
      "order": 47,
      "role": "OTHER",
      "version": "1.0.0"
    }
  ],
  "actors": [
    {
      "actor_type": "GROUP",
      "code": "GU-01",
      "description": "Лица, которые в рассматриваемом временном срезе непосредственно заняты в основных добывающих и иных ключевых нефтегазовых предприятиях региона. Не включает работников подрядчиков.",
      "id": "d31904bd-a9e2-52bc-886d-d959d8e6f86d",
      "label": "Штатные работники основных нефтегазовых предприятий",
      "order": 1,
      "parent_id": null,
      "version": "1.0.0"
    },
    {
      "actor_type": "GROUP",
      "code": "GU-02",
      "description": "Лица, занятые у подрядчиков, субподрядчиков, нефтесервисных и транспортно-сервисных организаций, обслуживающих нефтегазовый сектор.",
      "id": "4c215889-7a31-56ae-8a60-cc546c915241",
      "label": "Работники подрядных и нефтесервисных организаций",
      "order": 2,
      "parent_id": null,
      "version": "1.0.0"
    },
    {
      "actor_type": "GROUP",
      "code": "GU-03",
      "description": "Лица, не входящие в ГУ-01 и ГУ-02 на дату среза: уволенные и бывшие работники сектора, безработные и местные соискатели рабочих мест, включая ищущую занятость молодёжь.",
      "id": "6e5f84f6-8988-5e72-8fbd-bf67d4c8bb45",
      "label": "Уволенные, бывшие работники и безработные соискатели нефтегазовых рабочих мест",
      "order": 3,
      "parent_id": null,
      "version": "1.0.0"
    },
    {
      "actor_type": "GROUP",
      "code": "GU-04",
      "description": "Население Жанаозена и выбранной территории Мангистау, не вошедшее в ГУ-01–ГУ-03: в том числе бюджетники, пенсионеры, студенты, представители малого бизнеса и иные жители. При кодировании конкретное лицо не должно одновременно учитываться в нескольких социальных ГУ.",
      "id": "744feea3-d4d4-5a3c-9d65-394894389e67",
      "label": "Остальные жители исследуемой территории",
      "order": 4,
      "parent_id": null,
      "version": "1.0.0"
    },
    {
      "actor_type": "GROUP",
      "code": "GU-05",
      "description": "Руководство основных нефтегазовых предприятий, подрядных и нефтесервисных организаций, а также коллективные органы работодателей, принимающие решения по труду, оплате и найму.",
      "id": "d803888d-ec24-5c7e-905b-96f88d01c36f",
      "label": "Работодатели и руководство нефтегазовых компаний и подрядчиков",
      "order": 5,
      "parent_id": null,
      "version": "1.0.0"
    },
    {
      "actor_type": "GROUP",
      "code": "GU-06",
      "description": "Акимат Жанаозена, акимат Мангистауской области и иные местные/региональные органы, действующие в пределах исследуемой территории.",
      "id": "73e1643f-34d5-537d-8f78-bdf15c3b7c35",
      "label": "Местные и региональные органы власти",
      "order": 6,
      "parent_id": null,
      "version": "1.0.0"
    },
    {
      "actor_type": "GROUP",
      "code": "GU-07",
      "description": "Президент, администрация президента, правительство, профильные министерства и иные центральные органы, принимающие политические и административные решения по кейсу.",
      "id": "fd80f79b-7c39-58db-b122-7245b77ff0c5",
      "label": "Центральные органы государственной власти",
      "order": 7,
      "parent_id": null,
      "version": "1.0.0"
    },
    {
      "actor_type": "GROUP",
      "code": "GU-08",
      "description": "Полиция, Национальная гвардия, иные силовые подразделения, прокуратура, следственные органы и суды. В источниковой базе конкретные органы сохраняются раздельно, даже если в простой расчётной модели агрегируются в одну ГУ.",
      "id": "6782018f-1868-5aa7-b40e-fb5ad11269ca",
      "label": "Правоохранительные, силовые, судебные и надзорные органы",
      "order": 8,
      "parent_id": null,
      "version": "1.0.0"
    }
  ],
  "analytical_elements": [
    {
      "code": "PTN-01",
      "description": "Включает: розничную цену, резкость изменения цены, доступность топлива для населения и автомобильного транспорта, дефицит и ограничения продажи. Не включает: общую инфляцию и цены всех товаров, если они не рассматриваются как контекст.",
      "element_type": "CONFLICT_ISSUE",
      "id": "e4311a29-c1a3-5000-9af8-9603d268c7d1",
      "label": "Цена и доступность сжиженного нефтяного газа",
      "order": 1,
      "parent_id": null,
      "reference_statement": "Существующий уровень цены и физической доступности СУГ не требует существенного изменения.",
      "version": "1.0.0"
    },
    {
      "code": "PTN-02",
      "description": "Включает: заработную плату, надбавки, премии, социальный пакет, безопасность и базовые гарантии занятости работников нефтегазового сектора. Не включает: различия штатных и подрядных работников как отдельную ПТН-03.",
      "element_type": "CONFLICT_ISSUE",
      "id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
      "label": "Оплата труда и социальные гарантии работников нефтегазового сектора",
      "order": 2,
      "parent_id": null,
      "reference_statement": "Существующий порядок оплаты и социальных гарантий работников нефтегазового сектора является приемлемым и не требует существенного изменения.",
      "version": "1.0.0"
    },
    {
      "code": "PTN-03",
      "description": "Включает: различия в оплате, гарантиях, стабильности найма, социальных пакетах, оборудовании и условиях труда между работниками основных компаний и подрядных/нефтесервисных организаций.",
      "element_type": "STRUCTURAL_DRIVER",
      "id": "6e3f62f8-6e0b-5b92-8c7c-b37022610a1d",
      "label": "Неравенство условий штатных и подрядных работников",
      "order": 3,
      "parent_id": null,
      "reference_statement": "Различия в условиях основной и подрядной занятости допустимы и не требуют существенного выравнивания.",
      "version": "1.0.0"
    },
    {
      "code": "PTN-04",
      "description": "Включает: безработицу, массовые увольнения, смену подрядчика, прямой найм, трудоустройство местных жителей, доступ молодёжи и бывших работников к рабочим местам.",
      "element_type": "STRUCTURAL_DRIVER",
      "id": "2fecb360-274b-55da-a7d4-6020a87de286",
      "label": "Занятость местного населения и доступ к рабочим местам",
      "order": 4,
      "parent_id": null,
      "reference_statement": "Существующий доступ местных жителей к нефтегазовым рабочим местам достаточен и не требует существенного расширения.",
      "version": "1.0.0"
    },
    {
      "code": "PTN-05",
      "description": "Включает: деятельность профсоюзов и инициативных групп, доступ к переговорам и посредничеству, возможность коллективных обращений, собраний и законной забастовки, решения о законности акций.",
      "element_type": "PROCESS",
      "id": "728c8406-ba99-5787-9557-933b5670be7c",
      "label": "Представительство интересов, переговоры и коллективные действия",
      "order": 5,
      "parent_id": null,
      "reference_statement": "Существующие механизмы представительства, переговоров и коллективных действий обеспечивают достаточный доступ к выражению и согласованию интересов.",
      "version": "1.0.0"
    },
    {
      "code": "PTN-06",
      "description": "Включает: задержания, применение силы и оружия, чрезвычайные ограничения, судебное и прокурорское реагирование, расследования, ответственность, компенсации, признание последствий и коллективную память о событиях 2011 и 2022 годов.",
      "element_type": "INSTITUTIONAL_RESPONSE",
      "id": "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9",
      "label": "Государственное принуждение и постконфликтное правосудие",
      "order": 6,
      "parent_id": null,
      "reference_statement": "Существующие правоохранительные и судебные процедуры реагирования на трудовой конфликт достаточны и соразмерны с точки зрения данного актора.",
      "version": "1.0.0"
    }
  ],
  "format": "conflict-analysis-project-definition",
  "format_version": "1.0.0",
  "help_bindings": [],
  "parameter_definitions": [
    {
      "allowed_statuses": [
        "CONFIRMED",
        "PROVISIONAL",
        "DISPUTED",
        "UNKNOWN",
        "INSUFFICIENT_DATA",
        "NOT_APPLICABLE",
        "OPEN_METHOD",
        "RETROSPECTIVE_KNOWLEDGE"
      ],
      "applicability": {
        "actor_element_role_ids": [
          "40e5dfc7-8b76-5739-8e6a-6493a0099d23",
          "72c82424-75f8-5671-a8d5-42a99c276b12",
          "1e973d7c-f605-58b8-9db0-c505df2e67c9",
          "256afb8d-9067-5a1c-b449-b2ab2c101532",
          "4b3ffd2d-6511-5b21-bcfa-e5c5b2a123af",
          "e0aec73e-f274-5af1-a3f1-9e9bd2c498fc",
          "4d90697f-51ca-5984-a587-7a2566bca3e6",
          "b10a8d08-01a7-507d-8a2d-9ddb9b9e6649",
          "cb460ec1-500b-5162-b451-1c443531408e",
          "c7ce39ce-3bba-5d35-b89f-2cf1a761891c",
          "9b6528b2-3ea0-54a3-9bb7-d0304e324873",
          "aa8d038a-02af-5cbd-b5fa-f2dfafd76854",
          "17b64c83-df54-5f0f-bb81-ceaf58cc306f",
          "4a74d189-341c-5a73-a3c9-4b13dc0ed5b5",
          "53f74005-412c-57b4-a2a4-b230d76b2d3b",
          "bca2320f-53d4-5371-9183-b4e1778a5096",
          "6f92fafc-ca56-5035-870f-72fe0062dd04",
          "a6c938b5-c948-53c3-9c88-4eb20502f14a",
          "d729707b-4f73-554a-a0fa-cb9c6abd96b5",
          "156eecc1-4876-50bf-8beb-8fa0ec8e09f8",
          "591df5ca-7b2e-5c2f-a880-12e95e88d794",
          "ade9036e-50af-5add-866d-c096f365d9fd",
          "8f84cdb7-1f96-5827-a867-8f96825dc2c3",
          "446a5c74-f0a0-5cec-a795-c26d5da32d60",
          "e2df521c-538c-5a36-a9f3-7384e1d39644",
          "ce41ce1b-3bdb-54bd-8b17-b27224f40c95",
          "0c8423ba-07d4-597c-ae82-e64e2caa6336",
          "56fa106e-7397-53f0-adc6-5d2bd5181588",
          "a1423d44-63bf-5c1f-8260-2c2d8b40831d",
          "de3f65fb-2854-58a3-9916-4b69dbbd92a1",
          "f0935f81-8d39-5c89-8c58-8f578adf753f",
          "475213b5-e6cb-5c56-8d73-2f20ca3aad6b",
          "c3f93424-c2ae-507d-98ae-b83964164bc6",
          "3601f1ae-8422-50ad-ba34-8961fc891211",
          "12f46b6d-2600-56b6-811f-78ba077f16b7",
          "312a43a5-3ca7-51a3-ba63-e35c8440b1a1",
          "425cb4cf-20fd-5b32-8cf4-046bc56b2727",
          "d482ea59-37a7-5841-92cf-f576f187f474",
          "85bcda97-f661-594d-a926-6ef3c816e7f8",
          "9359e149-e276-5fb6-aa94-cf7f6f1379e9",
          "b1ae2d3d-e2ac-5e1f-8a9b-0a2741f6bafd",
          "1aef4911-d213-5bca-9458-43eac819391a",
          "a9a8064e-eedd-5c90-813f-09eb1842b0fb",
          "713d1cd0-57c5-5436-ada3-830bcb21d96a",
          "f9237dcf-877d-543c-a2d7-b0e980815be9",
          "ce11c754-dac0-5666-bd87-32eaa25d3615",
          "29c24ed9-ad6d-5d3b-87d5-08e218a90b23",
          "ff48151f-9a5d-5798-96a8-6595fdce6291"
        ],
        "actor_ids": [
          "d31904bd-a9e2-52bc-886d-d959d8e6f86d",
          "4c215889-7a31-56ae-8a60-cc546c915241",
          "6e5f84f6-8988-5e72-8fbd-bf67d4c8bb45",
          "744feea3-d4d4-5a3c-9d65-394894389e67",
          "d803888d-ec24-5c7e-905b-96f88d01c36f",
          "73e1643f-34d5-537d-8f78-bdf15c3b7c35",
          "fd80f79b-7c39-58db-b122-7245b77ff0c5",
          "6782018f-1868-5aa7-b40e-fb5ad11269ca"
        ],
        "analytical_element_ids": [
          "e4311a29-c1a3-5000-9af8-9603d268c7d1",
          "74872afd-9303-5d0f-a70a-d5fe7154645c",
          "6e3f62f8-6e0b-5b92-8c7c-b37022610a1d",
          "2fecb360-274b-55da-a7d4-6020a87de286",
          "728c8406-ba99-5787-9557-933b5670be7c",
          "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9"
        ]
      },
      "code": "POS",
      "description": "A3/A4 V4-TERM-2.0; PROPOSAL_FOR_FREEZE.",
      "id": "532433cb-1452-5354-929a-020679d3972d",
      "name": "позиция актора по вопросу",
      "reference_statement": "Интерпретация POS определяется только reference_statement связанного AnalyticalElement; это поле ParameterDefinition не задаёт самостоятельного содержательного утверждения.",
      "scale": {
        "maximum": "10",
        "minimum": "-10",
        "step": null
      },
      "target_type": "ACTOR_ELEMENT_ASSESSMENT",
      "value_type": "DECIMAL",
      "version": "V4-TERM-2.0"
    },
    {
      "allowed_statuses": [
        "CONFIRMED",
        "PROVISIONAL",
        "DISPUTED",
        "UNKNOWN",
        "INSUFFICIENT_DATA",
        "NOT_APPLICABLE",
        "OPEN_METHOD",
        "RETROSPECTIVE_KNOWLEDGE"
      ],
      "applicability": {
        "actor_element_role_ids": [
          "40e5dfc7-8b76-5739-8e6a-6493a0099d23",
          "72c82424-75f8-5671-a8d5-42a99c276b12",
          "1e973d7c-f605-58b8-9db0-c505df2e67c9",
          "256afb8d-9067-5a1c-b449-b2ab2c101532",
          "4b3ffd2d-6511-5b21-bcfa-e5c5b2a123af",
          "e0aec73e-f274-5af1-a3f1-9e9bd2c498fc",
          "4d90697f-51ca-5984-a587-7a2566bca3e6",
          "b10a8d08-01a7-507d-8a2d-9ddb9b9e6649",
          "cb460ec1-500b-5162-b451-1c443531408e",
          "c7ce39ce-3bba-5d35-b89f-2cf1a761891c",
          "9b6528b2-3ea0-54a3-9bb7-d0304e324873",
          "aa8d038a-02af-5cbd-b5fa-f2dfafd76854",
          "17b64c83-df54-5f0f-bb81-ceaf58cc306f",
          "4a74d189-341c-5a73-a3c9-4b13dc0ed5b5",
          "53f74005-412c-57b4-a2a4-b230d76b2d3b",
          "bca2320f-53d4-5371-9183-b4e1778a5096",
          "6f92fafc-ca56-5035-870f-72fe0062dd04",
          "a6c938b5-c948-53c3-9c88-4eb20502f14a",
          "d729707b-4f73-554a-a0fa-cb9c6abd96b5",
          "156eecc1-4876-50bf-8beb-8fa0ec8e09f8",
          "591df5ca-7b2e-5c2f-a880-12e95e88d794",
          "ade9036e-50af-5add-866d-c096f365d9fd",
          "8f84cdb7-1f96-5827-a867-8f96825dc2c3",
          "446a5c74-f0a0-5cec-a795-c26d5da32d60",
          "e2df521c-538c-5a36-a9f3-7384e1d39644",
          "ce41ce1b-3bdb-54bd-8b17-b27224f40c95",
          "0c8423ba-07d4-597c-ae82-e64e2caa6336",
          "56fa106e-7397-53f0-adc6-5d2bd5181588",
          "a1423d44-63bf-5c1f-8260-2c2d8b40831d",
          "de3f65fb-2854-58a3-9916-4b69dbbd92a1",
          "f0935f81-8d39-5c89-8c58-8f578adf753f",
          "475213b5-e6cb-5c56-8d73-2f20ca3aad6b",
          "c3f93424-c2ae-507d-98ae-b83964164bc6",
          "3601f1ae-8422-50ad-ba34-8961fc891211",
          "12f46b6d-2600-56b6-811f-78ba077f16b7",
          "312a43a5-3ca7-51a3-ba63-e35c8440b1a1",
          "425cb4cf-20fd-5b32-8cf4-046bc56b2727",
          "d482ea59-37a7-5841-92cf-f576f187f474",
          "85bcda97-f661-594d-a926-6ef3c816e7f8",
          "9359e149-e276-5fb6-aa94-cf7f6f1379e9",
          "b1ae2d3d-e2ac-5e1f-8a9b-0a2741f6bafd",
          "1aef4911-d213-5bca-9458-43eac819391a",
          "a9a8064e-eedd-5c90-813f-09eb1842b0fb",
          "713d1cd0-57c5-5436-ada3-830bcb21d96a",
          "f9237dcf-877d-543c-a2d7-b0e980815be9",
          "ce11c754-dac0-5666-bd87-32eaa25d3615",
          "29c24ed9-ad6d-5d3b-87d5-08e218a90b23",
          "ff48151f-9a5d-5798-96a8-6595fdce6291"
        ],
        "actor_ids": [
          "d31904bd-a9e2-52bc-886d-d959d8e6f86d",
          "4c215889-7a31-56ae-8a60-cc546c915241",
          "6e5f84f6-8988-5e72-8fbd-bf67d4c8bb45",
          "744feea3-d4d4-5a3c-9d65-394894389e67",
          "d803888d-ec24-5c7e-905b-96f88d01c36f",
          "73e1643f-34d5-537d-8f78-bdf15c3b7c35",
          "fd80f79b-7c39-58db-b122-7245b77ff0c5",
          "6782018f-1868-5aa7-b40e-fb5ad11269ca"
        ],
        "analytical_element_ids": [
          "e4311a29-c1a3-5000-9af8-9603d268c7d1",
          "74872afd-9303-5d0f-a70a-d5fe7154645c",
          "6e3f62f8-6e0b-5b92-8c7c-b37022610a1d",
          "2fecb360-274b-55da-a7d4-6020a87de286",
          "728c8406-ba99-5787-9557-933b5670be7c",
          "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9"
        ]
      },
      "code": "SAL",
      "description": "A3/A4 V4-TERM-2.0; PROPOSAL_FOR_FREEZE.",
      "id": "a223a247-d834-52fc-a156-e6acaf58b428",
      "name": "значимость вопроса для актора",
      "reference_statement": "Интерпретация SAL относится к тому же actor-element assessment и reference_statement связанного AnalyticalElement; это поле ParameterDefinition не задаёт самостоятельного содержательного утверждения.",
      "scale": {
        "maximum": "10",
        "minimum": "0",
        "step": null
      },
      "target_type": "ACTOR_ELEMENT_ASSESSMENT",
      "value_type": "DECIMAL",
      "version": "V4-TERM-2.0"
    }
  ],
  "policies": {
    "structure_lock": {
      "is_structure_locked": true,
      "ordinary_user_can_edit_structure": false,
      "reason": "FROZEN_FOR_DEMO_V1: изменение состава требует отдельного прямого OWNER_DECISION и новой версии перечня.",
      "studio_can_edit_structure": false
    }
  },
  "project": {
    "code": "KZ-ZHANAOZEN-DEMO",
    "default_locale": "ru",
    "description": "",
    "id": "3de70d1d-f4cf-535a-95b9-94c0a65e60e3",
    "metadata": {
      "actor_aliases": [
        {
          "aliases": "ГУ-01; Штатные нефтяники",
          "legacy_pk": "443ce826-c8a5-5b96-96df-89ae92a1e45b",
          "manifest_code": "GU-01",
          "manifest_label": "Штатные работники основных нефтегазовых предприятий",
          "manifest_type": "GROUP",
          "source_code": "KZ.ZHANAOZEN.ACTOR.GU01",
          "source_display_name": "Работники основных нефтегазовых предприятий",
          "source_token": "АК-01",
          "source_type": "SOCIAL_GROUP",
          "source_uuid": "d31904bd-a9e2-52bc-886d-d959d8e6f86d"
        },
        {
          "aliases": "ГУ-02; Подрядчики и нефтесервис",
          "legacy_pk": "6a5ba28b-5ab5-583d-b748-2688746b9e53",
          "manifest_code": "GU-02",
          "manifest_label": "Работники подрядных и нефтесервисных организаций",
          "manifest_type": "GROUP",
          "source_code": "KZ.ZHANAOZEN.ACTOR.GU02",
          "source_display_name": "Работники подрядных и нефтесервисных организаций",
          "source_token": "АК-02",
          "source_type": "SOCIAL_GROUP",
          "source_uuid": "4c215889-7a31-56ae-8a60-cc546c915241"
        },
        {
          "aliases": "ГУ-03; Уволенные и соискатели",
          "legacy_pk": "75f2877f-e1c1-5632-9197-4a378e72d263",
          "manifest_code": "GU-03",
          "manifest_label": "Уволенные, бывшие работники и безработные соискатели нефтегазовых рабочих мест",
          "manifest_type": "GROUP",
          "source_code": "KZ.ZHANAOZEN.ACTOR.GU03",
          "source_display_name": "Уволенные и соискатели нефтегазовой занятости",
          "source_token": "АК-03",
          "source_type": "SOCIAL_GROUP",
          "source_uuid": "6e5f84f6-8988-5e72-8fbd-bf67d4c8bb45"
        },
        {
          "aliases": "ГУ-04; Остальные жители",
          "legacy_pk": "1f4a9c44-ef18-5e28-bfce-369c066fd838",
          "manifest_code": "GU-04",
          "manifest_label": "Остальные жители исследуемой территории",
          "manifest_type": "GROUP",
          "source_code": "KZ.ZHANAOZEN.ACTOR.GU04",
          "source_display_name": "Жители территории вне нефтегазовых трудовых групп",
          "source_token": "АК-04",
          "source_type": "SOCIAL_GROUP",
          "source_uuid": "744feea3-d4d4-5a3c-9d65-394894389e67"
        },
        {
          "aliases": "ГУ-05; Работодатели",
          "legacy_pk": "35925786-e2cb-593e-8e9b-b3afe73373d9",
          "manifest_code": "GU-05",
          "manifest_label": "Работодатели и руководство нефтегазовых компаний и подрядчиков",
          "manifest_type": "GROUP",
          "source_code": "KZ.ZHANAOZEN.ACTOR.GU05",
          "source_display_name": "Работодатели нефтегазового сектора и подрядного контура",
          "source_token": "АК-05",
          "source_type": "ORGANIZATIONAL_ACTOR_GROUP",
          "source_uuid": "d803888d-ec24-5c7e-905b-96f88d01c36f"
        },
        {
          "aliases": "ГУ-06; Местная и региональная власть",
          "legacy_pk": "6666fe92-baac-55c5-92ab-016c15d9b984",
          "manifest_code": "GU-06",
          "manifest_label": "Местные и региональные органы власти",
          "manifest_type": "GROUP",
          "source_code": "KZ.ZHANAOZEN.ACTOR.GU06",
          "source_display_name": "Местные и региональные органы публичной власти",
          "source_token": "АК-06",
          "source_type": "PUBLIC_AUTHORITY_GROUP",
          "source_uuid": "73e1643f-34d5-537d-8f78-bdf15c3b7c35"
        },
        {
          "aliases": "ГУ-07; Центральная власть",
          "legacy_pk": "fef85cd8-2cf3-5861-821e-5fd6c3cd8c13",
          "manifest_code": "GU-07",
          "manifest_label": "Центральные органы государственной власти",
          "manifest_type": "GROUP",
          "source_code": "KZ.ZHANAOZEN.ACTOR.GU07",
          "source_display_name": "Центральные органы государственной власти",
          "source_token": "АК-07",
          "source_type": "PUBLIC_AUTHORITY_GROUP",
          "source_uuid": "fd80f79b-7c39-58db-b122-7245b77ff0c5"
        },
        {
          "aliases": "ГУ-08; Силовые и правовые органы",
          "legacy_pk": "546b1f66-c6c6-565d-91d0-b2bf2f501835",
          "manifest_code": "GU-08",
          "manifest_label": "Правоохранительные, силовые, судебные и надзорные органы",
          "manifest_type": "GROUP",
          "source_code": "KZ.ZHANAOZEN.ACTOR.GU08",
          "source_display_name": "Правоохранительные, судебные и надзорные органы",
          "source_token": "АК-08",
          "source_type": "PUBLIC_AUTHORITY_GROUP",
          "source_uuid": "6782018f-1868-5aa7-b40e-fb5ad11269ca"
        }
      ],
      "element_aliases": [
        {
          "legacy_pk": "42961f37-def0-5a6f-95bf-fc7c100d6293",
          "manifest_code": "PTN-01",
          "manifest_label": "Цена и доступность сжиженного нефтяного газа",
          "manifest_type": "CONFLICT_ISSUE",
          "reference_statement": "Существующий уровень цены и физической доступности СУГ не требует существенного изменения.",
          "source_code": "KZ.ZHANAOZEN.ELEMENT.E01",
          "source_display_name": "Цена и доступность сжиженного нефтяного газа",
          "source_token": "КВК-01",
          "source_type": "STRUCTURAL_DRIVER",
          "source_uuid": "e4311a29-c1a3-5000-9af8-9603d268c7d1"
        },
        {
          "legacy_pk": "cf3f84f8-a9bb-577d-a05b-588688f6e70c",
          "manifest_code": "PTN-02",
          "manifest_label": "Оплата труда и социальные гарантии работников нефтегазового сектора",
          "manifest_type": "CONFLICT_ISSUE",
          "reference_statement": "Существующий порядок оплаты и социальных гарантий работников нефтегазового сектора является приемлемым и не требует существенного изменения.",
          "source_code": "KZ.ZHANAOZEN.ELEMENT.E02",
          "source_display_name": "Оплата труда и социальные гарантии в нефтегазовом секторе",
          "source_token": "КВК-02",
          "source_type": "CONFLICT_ISSUE",
          "source_uuid": "74872afd-9303-5d0f-a70a-d5fe7154645c"
        },
        {
          "legacy_pk": "0cdf4eaf-1460-5fb5-8f44-d1e547272935",
          "manifest_code": "PTN-03",
          "manifest_label": "Неравенство условий штатных и подрядных работников",
          "manifest_type": "STRUCTURAL_DRIVER",
          "reference_statement": "Различия в условиях основной и подрядной занятости допустимы и не требуют существенного выравнивания.",
          "source_code": "KZ.ZHANAOZEN.ELEMENT.E03",
          "source_display_name": "Неравенство условий основной и подрядной занятости",
          "source_token": "КВК-03",
          "source_type": "GRIEVANCE",
          "source_uuid": "6e3f62f8-6e0b-5b92-8c7c-b37022610a1d"
        },
        {
          "legacy_pk": "e9e6b771-29a6-5193-a395-aa367ffe782d",
          "manifest_code": "PTN-04",
          "manifest_label": "Занятость местного населения и доступ к рабочим местам",
          "manifest_type": "STRUCTURAL_DRIVER",
          "reference_statement": "Существующий доступ местных жителей к нефтегазовым рабочим местам достаточен и не требует существенного расширения.",
          "source_code": "KZ.ZHANAOZEN.ELEMENT.E04",
          "source_display_name": "Доступ местных жителей к нефтегазовой занятости",
          "source_token": "КВК-04",
          "source_type": "STRUCTURAL_DRIVER",
          "source_uuid": "2fecb360-274b-55da-a7d4-6020a87de286"
        },
        {
          "legacy_pk": "90e144e5-e9c9-5bd9-ba3a-57c35ff32d57",
          "manifest_code": "PTN-05",
          "manifest_label": "Представительство интересов, переговоры и коллективные действия",
          "manifest_type": "PROCESS",
          "reference_statement": "Существующие механизмы представительства, переговоров и коллективных действий обеспечивают достаточный доступ к выражению и согласованию интересов.",
          "source_code": "KZ.ZHANAOZEN.ELEMENT.E05",
          "source_display_name": "Представительство интересов и доступ к коллективным переговорам",
          "source_token": "КВК-05",
          "source_type": "PROCESS",
          "source_uuid": "728c8406-ba99-5787-9557-933b5670be7c"
        },
        {
          "legacy_pk": "2cba655c-2892-51bb-9651-81339291d344",
          "manifest_code": "PTN-06",
          "manifest_label": "Государственное принуждение и постконфликтное правосудие",
          "manifest_type": "INSTITUTIONAL_RESPONSE",
          "reference_statement": "Существующие правоохранительные и судебные процедуры реагирования на трудовой конфликт достаточны и соразмерны с точки зрения данного актора.",
          "source_code": "KZ.ZHANAOZEN.ELEMENT.E06",
          "source_display_name": "Государственное принуждение и правовые процедуры в конфликте",
          "source_token": "КВК-06",
          "source_type": "INSTITUTIONAL_RESPONSE",
          "source_uuid": "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9"
        }
      ],
      "role_policy": {
        "authority": "https://github.com/dshatrov7575-max/Conflict/issues/90#issuecomment-5598921736",
        "note": "Technical applicability bridge only; no substantive actor-role classification."
      },
      "seed_version": "KZ-ZHANAOZEN-TYPED-1.0.0",
      "source_ledger": {
        "A3": {
          "filename": "A3_CANONICAL_GLOSSARY_V4_TERM_2_0.md",
          "raw_bytes": 5792,
          "sha256": "314ac6facb41ba532e475fb008bc8f97ba0b43df26cf0c194782cc24d93f5fff",
          "status": "PROPOSAL_FOR_FREEZE"
        },
        "A4": {
          "filename": "A4_CODING_MANUAL_V4_TERM_2_0.md",
          "raw_bytes": 5914,
          "sha256": "ce45cc4d6a43950c8ae6d7a54a9a1a6646f7d80340d246d706588ee7060ab826",
          "status": "PROPOSAL_FOR_FREEZE"
        },
        "A5": {
          "drive_id": "1XGethGXRRKQNba8151M1awT3O6tChGiy",
          "raw_bytes": 198259,
          "sha256": "ba5dd521d61bb14d9e7f3883732d9685c79774430d4b1e3ac91f656a01744876",
          "status": "PROPOSAL / NOT_OWNER_APPROVED"
        },
        "cp3_json": {
          "drive_id": "1OIIV7gEBMcXk9qV1AHPp_8RabNmefi4p",
          "raw_bytes": 159511,
          "raw_sha256": "3a24135df10f1610854478b4526b176d6c3f912a8837044fecf700b04e147256"
        },
        "cp3_xlsx": {
          "drive_id": "1QbPyyXk09RrMoFiFsxXknZyiky4TTFyM",
          "raw_bytes": 51240,
          "raw_sha256": "04a5098cdbcbed580f9f71ce0b28c0a4f50fbae48a97f579274556bcf26030df"
        }
      }
    },
    "name": "Жанаозен / Западный Казахстан",
    "version": "1.0.0"
  }
}
'''

def manifest():
    """Return a fresh copy of the accepted immutable payload."""
    return json.loads(_MANIFEST_JSON)

_WORKSPACE_JSON = r'''
{
  "code": "ZHANAOZEN-TYPED-1.0.0",
  "id": "c6e16836-d003-5e6d-9294-932d25e06e3a",
  "label": "Жанаозен — каноническая структура V4",
  "metadata": {
    "installation_contract": "ZHANAOZEN_TYPED_MANIFEST_BOOTSTRAP_V1",
    "source_manifest_sha256": "6f149d681d4413d0e8f5cb61c2ed790cf277a385b900b2db35395794c94391ca"
  },
  "project_definition_hash": "6f149d681d4413d0e8f5cb61c2ed790cf277a385b900b2db35395794c94391ca",
  "project_definition_version_id": "08042667-fae6-5f3a-a248-514b9001e088",
  "version": "1.0.0"
}
'''

def workspace():
    """Return a fresh copy of the accepted immutable payload."""
    return json.loads(_WORKSPACE_JSON)

_SYSTEM_AUDIT_JSON = r'''
{
  "action": "CREATE",
  "actor_identifier": "SYSTEM:ZHANAOZEN_TYPED_MANIFEST_BOOTSTRAP_V1",
  "actor_type": "SYSTEM",
  "after": {
    "actor_identifier": "SYSTEM:ZHANAOZEN_TYPED_MANIFEST_BOOTSTRAP_V1",
    "actor_type": "SYSTEM",
    "audit_event_id": "156cac68-c08c-55c3-b041-fe051779e45b",
    "contract": "FOUNDATION_ZHANAOZEN_SYSTEM_PROJECTION_V1",
    "definition_id": "08042667-fae6-5f3a-a248-514b9001e088",
    "foundation_audit_context": {
      "actor_identifier": "SYSTEM:ZHANAOZEN_TYPED_MANIFEST_BOOTSTRAP_V1",
      "service_purpose": "CA-SUITE-I1-G8-PRE-CANONICAL-ZHANAOZEN-MANIFEST-001"
    },
    "installation_result": "COMPLETE",
    "manifest_sha256": "6f149d681d4413d0e8f5cb61c2ed790cf277a385b900b2db35395794c94391ca",
    "operation_id": "e03c577a-1e8c-5910-a724-2ea3a0ca12c5",
    "project_id": "3de70d1d-f4cf-535a-95b9-94c0a65e60e3",
    "projected_counts": {
      "actor_element_roles": 48,
      "actors": 8,
      "analytical_elements": 6,
      "parameter_definitions": 2
    },
    "projection_sha256": "0e16272fdef4458116ef3f9d6dc4528ca426782b8de49bb31ce52a9d371060c8",
    "request": {
      "definition_id": "08042667-fae6-5f3a-a248-514b9001e088",
      "manifest_sha256": "6f149d681d4413d0e8f5cb61c2ed790cf277a385b900b2db35395794c94391ca",
      "operation_id": "e03c577a-1e8c-5910-a724-2ea3a0ca12c5",
      "project_id": "3de70d1d-f4cf-535a-95b9-94c0a65e60e3",
      "projection_sha256": "0e16272fdef4458116ef3f9d6dc4528ca426782b8de49bb31ce52a9d371060c8",
      "service_capabilities": [
        "DEFINITION_PUBLISH",
        "DEFINITION_VALIDATE",
        "DRAFT_CREATE",
        "STRUCTURE_MUTATE"
      ],
      "service_principal": "SYSTEM:ZHANAOZEN_TYPED_MANIFEST_BOOTSTRAP_V1",
      "service_purpose": "CA-SUITE-I1-G8-PRE-CANONICAL-ZHANAOZEN-MANIFEST-001",
      "snapshot_sha256": "21cc76682c2a768cf40b0ce6e6f564cff517128cd66c50b379646c2513bbbf78",
      "source_mapping_sha256": "619c239fb81102c3f37ef91abfd12e06703458dacfc15a7179ec1cfb999f199f",
      "workspace_id": "c6e16836-d003-5e6d-9294-932d25e06e3a"
    },
    "request_sha256": "5219dafe359936ffa506c4357a3cf707df6d8c2cbb10d21bf5c1315be513910c",
    "snapshot_sha256": "21cc76682c2a768cf40b0ce6e6f564cff517128cd66c50b379646c2513bbbf78",
    "source_counts": {
      "actor_element_roles": 48,
      "actors": 8,
      "analytical_elements": 6,
      "parameter_definitions": 2
    },
    "source_mapping_sha256": "619c239fb81102c3f37ef91abfd12e06703458dacfc15a7179ec1cfb999f199f",
    "version": "1.0.0",
    "workspace_id": "c6e16836-d003-5e6d-9294-932d25e06e3a"
  },
  "before": null,
  "code": "ZHANAOZEN-SYSTEM-PROJECTION-e03c577a-1e8c-5910-a724-2ea3a0ca12c5",
  "entity_id": "c6e16836-d003-5e6d-9294-932d25e06e3a",
  "entity_type": "FOUNDATION_ZHANAOZEN_SYSTEM_PROJECTION_V1",
  "id": "156cac68-c08c-55c3-b041-fe051779e45b",
  "project_id": "3de70d1d-f4cf-535a-95b9-94c0a65e60e3",
  "scope": "WORKSPACE",
  "version": "1.0.0",
  "workspace_id": "c6e16836-d003-5e6d-9294-932d25e06e3a"
}
'''

def system_audit():
    """Return a fresh copy of the accepted immutable payload."""
    return json.loads(_SYSTEM_AUDIT_JSON)

_TIME_SLICES_JSON = r'''
[
  {
    "a5_token": "2011",
    "code": "2011-12-15",
    "cutoff_date": "2011-12-15",
    "legacy_pk": "854b6a04-ebd1-5b14-b43e-89afd64e1720",
    "name": "PROJECT_DEFINITION_MANIFEST_V1:TIME_SLICE:2011-12-15",
    "namespace": "c6e16836-d003-5e6d-9294-932d25e06e3a",
    "order": 1,
    "typed_pk": "1b2c1f20-de7f-501c-904a-d8b015f5ff10",
    "version": "1.0.0"
  },
  {
    "a5_token": "2022",
    "code": "2022-01-02",
    "cutoff_date": "2022-01-02",
    "legacy_pk": "3554ef55-8503-51b9-8123-d743b6b91292",
    "name": "PROJECT_DEFINITION_MANIFEST_V1:TIME_SLICE:2022-01-02",
    "namespace": "c6e16836-d003-5e6d-9294-932d25e06e3a",
    "order": 2,
    "typed_pk": "d73f0fe9-0730-532d-b8c9-0f4e2c6a04b1",
    "version": "1.0.0"
  },
  {
    "a5_token": "2026",
    "code": "2026-08-21",
    "cutoff_date": "2026-08-21",
    "legacy_pk": "f83b6bb5-497a-58f0-97ab-d128014749c4",
    "name": "PROJECT_DEFINITION_MANIFEST_V1:TIME_SLICE:2026-08-21",
    "namespace": "c6e16836-d003-5e6d-9294-932d25e06e3a",
    "order": 3,
    "typed_pk": "958ce86e-cae9-5317-85f1-62d22ece365e",
    "version": "1.0.0"
  }
]
'''

def time_slices():
    """Return a fresh copy of the accepted immutable payload."""
    return json.loads(_TIME_SLICES_JSON)

