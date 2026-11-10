-- Capri MCP Bridge
-- CET side of the Capri MCP control plane. It polls a small line-based command
-- file in Capri's storage folder and answers through the CapriSystem public API.
-- No keys are read or returned; provider keys stay in the game's settings.
--
-- Install as:
--   bin/x64/plugins/cyber_engine_tweaks/mods/CapriMcpBridge/init.lua
-- It only acts while a save with CapriSystem is loaded.

local unpack = table.unpack or unpack

local function script_directory()
    local source = debug.getinfo(1, "S").source or ""
    if source:sub(1, 1) == "@" then source = source:sub(2) end
    return source:match("^(.*)[/\\][^/\\]+$") or "."
end

local MOD_DIR = script_directory()
local GAME_DIR = MOD_DIR:match(
    "^(.*)[/\\]bin[/\\]x64[/\\]plugins[/\\]cyber_engine_tweaks[/\\]mods[/\\][^/\\]+$"
)
local STORAGE_DIR = (GAME_DIR and (GAME_DIR .. "/r6/storages/CapriConstruct"))
    or "r6/storages/CapriConstruct"
local COMMAND_FILE = STORAGE_DIR .. "/mcp_command.txt"
local RESULT_FILE = STORAGE_DIR .. "/mcp_result.txt"
local POLL_SECONDS = 0.1
local last_id = nil
local last_poll = 0

local function read_text(path)
    local file = io.open(path, "rb")
    if not file then return nil end
    local text = file:read("*a")
    file:close()
    return text
end

local function write_text(path, text)
    local file = io.open(path, "wb")
    if not file then return false end
    file:write(text)
    file:close()
    return true
end

local function unescape(value)
    local out = {}
    local i = 1
    while i <= #value do
        local char = value:sub(i, i)
        if char == "\\" and i < #value then
            local next_char = value:sub(i + 1, i + 1)
            if next_char == "n" then
                out[#out + 1] = "\n"
                i = i + 2
            elseif next_char == "r" then
                out[#out + 1] = "\r"
                i = i + 2
            elseif next_char == "\\" then
                out[#out + 1] = "\\"
                i = i + 2
            else
                out[#out + 1] = next_char
                i = i + 2
            end
        else
            out[#out + 1] = char
            i = i + 1
        end
    end
    return table.concat(out)
end

local function escape(value)
    return tostring(value):gsub("\\", "\\\\"):gsub("\r", "\\r"):gsub("\n", "\\n")
end

local function parse_command(text)
    local command = {}
    for line in text:gmatch("[^\r\n]+") do
        local key, value = line:match("^([^=]+)=(.*)$")
        if key then command[key] = unescape(value) end
    end
    return command
end

local function write_result(result)
    local lines = { "id=" .. escape(result.id or ""), "ok=" .. (result.ok and "1" or "0") }
    for key, value in pairs(result) do
        if key ~= "id" and key ~= "ok" and value ~= nil then
            lines[#lines + 1] = key .. "=" .. escape(value)
        end
    end
    return write_text(RESULT_FILE, table.concat(lines, "\n") .. "\n")
end

local function get_system()
    local ok, system = pcall(function()
        return Game.GetScriptableSystemsContainer():Get(CName.new("Capri.CapriSystem"))
    end)
    if ok then return system end
    return nil
end

local function call(system, method, ...)
    local args = { ... }
    local ok, value = pcall(function()
        return system[method](system, unpack(args))
    end)
    if ok then return value end
    return nil
end

local function as_bool(value)
    if value == true then return 1 end
    if value == false then return 0 end
    return value
end

local function status_fields(system, result)
    local fields = {
        { "provider", "GetProvider" },
        { "p2State", "GetP2State" },
        { "p2Status", "GetP2Status" },
        { "p2Code", "GetP2Code" },
        { "p2Url", "GetP2Url" },
        { "voiceSource", "GetVoiceSource" },
        { "voiceStatus", "GetVoiceStatus" },
        { "hud", "GetHud" },
        { "missing", "GetMissingSetup" },
        { "hasApiKey", "HasApiKey" },
        { "hasGeminiKey", "HasGeminiKey" },
        { "hasOpenRouterKey", "HasOpenRouterKey" },
        { "model", "GetModel" },
        { "apiUrl", "GetApiUrl" },
        { "uiLanguage", "GetUiLanguage" },
        { "motor", "GetMotorState" },
        { "situation", "GetSituation" },
    }
    for _, field in ipairs(fields) do
        local value = call(system, field[2])
        if value ~= nil then result[field[1]] = as_bool(value) end
    end
end

local function with_status(system)
    local result = { ok = true }
    status_fields(system, result)
    return result
end

local actions = {}

actions.ping = function()
    local in_save = false
    pcall(function() in_save = Game.GetPlayer() ~= nil end)
    return { ok = true, bridge = 1, inSave = in_save and 1 or 0 }
end

actions.status = function()
    local system = get_system()
    if not system then
        return { ok = false, error = "CapriSystem not found; load a save with the Capri mod." }
    end
    return with_status(system)
end

actions.connect_player2 = function()
    local system = get_system()
    if not system then
        return { ok = false, error = "CapriSystem not found; load a save with the Capri mod." }
    end
    call(system, "ConnectPlayer2")
    return with_status(system)
end

actions.cancel_player2 = function()
    local system = get_system()
    if not system then return { ok = false, error = "CapriSystem not found." } end
    call(system, "CancelPlayer2")
    return with_status(system)
end

actions.disconnect_player2 = function()
    local system = get_system()
    if not system then return { ok = false, error = "CapriSystem not found." } end
    call(system, "DisconnectPlayer2")
    return with_status(system)
end

actions.set_provider = function(command)
    local system = get_system()
    if not system then return { ok = false, error = "CapriSystem not found." } end
    if not command.provider or command.provider == "" then
        return { ok = false, error = "provider is required" }
    end
    call(system, "SetProvider", command.provider)
    return with_status(system)
end

actions.set_api_url = function(command)
    local system = get_system()
    if not system then return { ok = false, error = "CapriSystem not found." } end
    call(system, "SetApiUrl", command.url or "")
    return with_status(system)
end

actions.set_model = function(command)
    local system = get_system()
    if not system then return { ok = false, error = "CapriSystem not found." } end
    call(system, "SetModel", command.model or "")
    return with_status(system)
end

actions.test_voice = function()
    local system = get_system()
    if not system then return { ok = false, error = "CapriSystem not found." } end
    call(system, "TestVoice")
    return { ok = true }
end

actions.summon = function()
    local system = get_system()
    if not system then return { ok = false, error = "CapriSystem not found." } end
    call(system, "Summon")
    return { ok = true }
end

actions.test_hud = function(command)
    local system = get_system()
    if not system then return { ok = false, error = "CapriSystem not found." } end
    local text = command.text
    if not text or text == "" then text = "Capri online. Can you see me, V?" end
    local mood = command.mood
    if not mood or mood == "" then mood = "teasing" end
    call(system, "TestHud", text, mood)
    return { ok = true }
end

actions.set_hud = function(command)
    local system = get_system()
    if not system then return { ok = false, error = "CapriSystem not found." } end
    call(system, "SetHud", command.value == "1" or command.value == "true")
    return with_status(system)
end

actions.set_voice_source = function(command)
    local system = get_system()
    if not system then return { ok = false, error = "CapriSystem not found." } end
    call(system, "SetVoiceSource", command.value or "auto")
    return with_status(system)
end

actions.fetch_models = function()
    local system = get_system()
    if not system then return { ok = false, error = "CapriSystem not found." } end
    call(system, "FetchModels")
    return with_status(system)
end

local function poll()
    local text = read_text(COMMAND_FILE)
    if not text or text == "" then return end
    local command = parse_command(text)
    if not command.id or command.id == "" or command.id == last_id then return end
    last_id = command.id

    local action = actions[command.action]
    local result
    if action then
        local ok, value = pcall(action, command)
        if ok and type(value) == "table" then
            result = value
        else
            result = { ok = false, error = tostring(value) }
        end
    else
        result = { ok = false, error = "unknown action: " .. tostring(command.action) }
    end
    result.id = command.id
    write_result(result)
end

registerForEvent("onUpdate", function()
    local now = os.clock()
    if now - last_poll < POLL_SECONDS then return end
    last_poll = now
    poll()
end)

registerForEvent("onInit", function()
    print("[CapriMcpBridge] ready; command=" .. COMMAND_FILE)
end)
