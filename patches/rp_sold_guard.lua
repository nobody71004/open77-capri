-- In resources/opx_infinity/modules/ripperdoc/module.lua, the existing unsold
-- guard is:
	if type(entry) ~= 'table' or entry.KIND ~= 'rp' then return false end

-- The patcher adds this immediately after it:
	if entry.RP_SOLD == true then return false end

-- This makes the explicit RP_SOLD=true opt-in bypass the "unsold" filter while
-- leaving every other rp item unchanged.
