-- Capri Voz Ready
-- CET resource for Capri: Personality Construct.
--
-- CapriVoz is started by the Capri RED4ext plugin when the game loads. CET is
-- sandboxed: os.execute and os.getenv are removed, so a CET resource cannot
-- launch a process. This resource does the part CET can do: after a save loads,
-- it calls Capri's own public health check through SetVoiceSource(current). That
-- calls CapriPlayer2.CheckCapriVoz(), and a moving heartbeat clears the automatic
-- "Capri Voz closed" cooldown without speaking a test line.
--
-- Install as:
--   bin/x64/plugins/cyber_engine_tweaks/mods/CapriVozReady/init.lua

local VERSION = "1.0.0"

local unpack = table.unpack or unpack

local last_system = nil
local stage = 0
local due = 0
local source = ""

local function system()
    local ok, value = pcall(function()
        return Game.GetScriptableSystemsContainer():Get(CName.new("Capri.CapriSystem"))
    end)
    if ok then return value end
    return nil
end

local function in_save()
    local ok, player = pcall(function()
        return Game.GetPlayer()
    end)
    return ok and player ~= nil
end

local function call(sys, method, ...)
    local args = { ... }
    local ok, value = pcall(function()
        return sys[method](sys, unpack(args))
    end)
    if ok then return true, value end
    return false, value
end

registerForEvent("onUpdate", function()
    local sys = system()
    if not sys or not in_save() then
        -- Main menu / no Capri system yet: re-arm for the next save.
        stage = 0
        last_system = nil
        return
    end

    if sys ~= last_system then
        -- Give the RED4ext plugin time to start CapriVoz before checking.
        last_system = sys
        stage = 1
        due = os.time() + 4
        return
    end

    if stage == 1 and os.time() >= due then
        local ok, current = call(sys, "GetVoiceSource")
        if not ok then
            print("[CapriVozReady] GetVoiceSource failed: " .. tostring(current))
            stage = 3
            return
        end

        source = tostring(current or "auto")
        if source ~= "player2" then
            local set_ok, set_error = call(sys, "SetVoiceSource", source)
            if not set_ok then
                print("[CapriVozReady] SetVoiceSource failed: " .. tostring(set_error))
                stage = 3
                return
            end
        end
        stage = 2
        due = os.time() + 3
    elseif stage == 2 and os.time() >= due then
        local ok, status = call(sys, "GetVoiceStatus")
        print("[CapriVozReady] " .. source .. ": " .. tostring(ok and status or "status unavailable"))
        stage = 3
    end
end)

return { version = VERSION }
