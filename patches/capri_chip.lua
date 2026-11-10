-- Inserted at the end of the CATALOG table in
-- resources/opx_infinity/config/ripperdoc.lua by patch_capri_clinic.py.
		{
			-- Capri Personality Construct: a forbidden Arasaka chip.
			-- The Capri client package supplies her mind and voice; the
			-- clinic owns the OS slot, the price, the capacity and the ledger.
			id = 'capri_personality_construct',
			NAME = 'ripperdoc.item.capri',
			DESC = 'ripperdoc.cw.capri_personality_construct.desc',
			ICON = 'cw_cyberdeck_arasaka',
			SYSTEM = 'operating_system', KIND = 'rp', TIER = 4, CAPACITY = 16,
			SLOT = 'operating_system',
			RP_SOLD = true,
			REMOVE = 250,
			WEAR = 2,
			GRADES = {
				{ id = 'prototype', NAME = 'ripperdoc.grade.capri.prototype', PRICE = 2500 },
			},
		},
