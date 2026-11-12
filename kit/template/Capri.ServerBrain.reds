// @@WORLD@@: Capri thinks with the brain on the game server's own machine.
//
// This file travels in the server's Capri package (requiredMods: the Open77 launcher installs it when a
// player joins), so every player's Capri is wired to that brain at game start: no Player2 app, no key,
// nothing to set up. Without it a new player's Capri starts on Player2, Capri's default, and greets with
// "I'm here, V, but disconnected". The launcher may not ship r6/storages (settings.json), hence a script.
//
// Written by the XyberRP Capri kit (kit/capri_kit.py in open77-capri), which puts in the brain's address
// as the server's own web server serves it, after checking it answers from the player's side. Change the
// kit, not this file: every build writes it again.
//
// When Capri reads settings.json, the player's own choice stays when it is a service of their own:
// OpenRouter, Gemini or OpenAI with their key, a custom service with its address and model, or a local
// AI at an address and model of their own. Everything else thinks with this server's brain: Player2 (the
// default), a service chosen without its key, a local AI without its model, this brain at an older
// address. What was decided at this start is written to r6/storages/CapriConstruct/server_brain.json
// (never an address or a key): the package, what the settings had, what she thinks with now and why.
module Capri

public class CapriServerBrain {
    // Put in by the kit when it builds the package.
    public static func Package() -> String { return "@@PACKAGE@@"; }
    public static func World() -> String { return "@@WORLD@@"; }
    public static func Url() -> String { return "@@URL@@"; }
    public static func Host() -> String { return "@@HOST@@"; }
    public static func Model() -> String { return "capri-brain"; }

    // Why her settings think with this server's brain; "" when the player's own choice stays.
    public static func Why(s: ref<CapriSettingsDTO>) -> String {
        let p = s.provider;
        if Equals(p, "openrouter") {
            return StrLen(s.openrouterKey) > 0 ? "" : "OpenRouter was chosen without a key";
        }
        if Equals(p, "gemini") {
            return StrLen(s.geminiKey) > 0 ? "" : "Gemini was chosen without a key";
        }
        if Equals(p, "openai") {
            return StrLen(s.openaiKey) > 0 ? "" : "OpenAI was chosen without a key";
        }
        if Equals(p, "custom") {
            return StrLen(s.customUrl) > 0 && StrLen(s.customModel) > 0 ? "" : "a custom service without its address or model";
        }
        if Equals(p, "local") {
            if Equals(s.localModel, CapriServerBrain.Model()) {
                return Equals(s.localUrl, CapriServerBrain.Url()) ? "already this brain" : "this brain at an older address";
            }
            return StrLen(s.localModel) > 0 && StrLen(s.localUrl) > 0 ? "" : "a local AI without its model";
        }
        // "player2", her default: without the Player2 app she is "here, but disconnected"
        return "Player2, the default";
    }

    public static func Wire(storage: ref<CapriStorage>, s: ref<CapriSettingsDTO>) -> Void {
        let before = s.provider;
        let why = CapriServerBrain.Why(s);
        let server = StrLen(why) > 0 && StrLen(CapriServerBrain.Url()) > 0;
        if server {
            s.provider = "local";
            s.localUrl = CapriServerBrain.Url();
            s.localModel = CapriServerBrain.Model();
        }
        let now = server ? "this server's brain" : "the player's own " + before;
        let because = server ? why : (StrLen(why) > 0 ? "no brain address in this package" : "a service of the player's own, kept");
        storage.WriteFile("server_brain.json", "{\"package\":\"" + CapriServerBrain.Package()
            + "\",\"world\":\"" + CapriServerBrain.World()
            + "\",\"brain\":\"" + CapriServerBrain.Host()
            + "\",\"model\":\"" + CapriServerBrain.Model()
            + "\",\"settingsHad\":\"" + before
            + "\",\"thinksWith\":\"" + now
            + "\",\"why\":\"" + because + "\"}");
        FTLog("[Capri] " + CapriServerBrain.World() + " " + CapriServerBrain.Package() + ": thinks with " + now + " (" + because + ")");
    }
}
@@HOOK@@
