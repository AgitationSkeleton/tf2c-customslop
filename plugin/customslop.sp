/**
 * CustomSlop announcer.
 *
 * Reads addons/sourcemod/configs/customslop/today.cfg (written by the nightly apply step):
 *   "CustomSlop" { "date" "2026-11-16"  "ad" "Today's 3 new weapons: ..." }
 * - prints the ad to chat every customslop_ad_interval seconds (default 300); the ad only ever
 *   lists weapons the apply step put live
 * - adds the live CustomSlop assets (configs/customslop/downloads.txt, written by apply) to the
 *   client download table at every map start, so FastDL serves them
 * - tells a player once per connection how to fix a stale client schema (#TF_Default_ItemDef)
 * It does nothing else: no hostname handling, no items (the schema does all the weapon work).
 */
#include <sourcemod>
#include <sdktools_stringtables>

#pragma semicolon 1
#pragma newdecls required

#define CFG "configs/customslop/today.cfg"
#define DL  "configs/customslop/downloads.txt"

ConVar g_cvInterval, g_cvEnabled;
char g_sAd[512];
Handle g_hTimer;

public Plugin myinfo =
{
    name = "CustomSlop announcer",
    author = "Vio's Arcade",
    description = "Daily CustomSlop weapons: chat ad",
    version = "0.3.0",
    url = "https://github.com/AgitationSkeleton/tf2c-customslop"
};

public void OnPluginStart()
{
    g_cvEnabled = CreateConVar("customslop_enabled", "1", "Show the CustomSlop chat ad");
    g_cvInterval = CreateConVar("customslop_ad_interval", "300", "Seconds between chat ads", _, true, 30.0);
    RegAdminCmd("sm_customslop_reload", Cmd_Reload, ADMFLAG_CONFIG, "Re-read today.cfg");
    g_cvInterval.AddChangeHook(OnIntervalChanged);
}

public void OnConfigsExecuted()
{
    LoadToday();
    RestartTimer();
}

public void OnMapStart()
{
    char path[PLATFORM_MAX_PATH], line[PLATFORM_MAX_PATH];
    BuildPath(Path_SM, path, sizeof(path), DL);
    File f = OpenFile(path, "r");
    if (f == null)
        return;
    int n = 0;
    while (!f.EndOfFile() && f.ReadLine(line, sizeof(line)))
    {
        TrimString(line);
        if (line[0] && FileExists(line, true))
        {
            AddFileToDownloadsTable(line);
            n++;
        }
    }
    delete f;
    LogMessage("CustomSlop: %d file(s) added to the download table", n);
}

void LoadToday()
{
    g_sAd[0] = '\0';
    char path[PLATFORM_MAX_PATH];
    BuildPath(Path_SM, path, sizeof(path), CFG);
    KeyValues kv = new KeyValues("CustomSlop");
    if (kv.ImportFromFile(path))
        kv.GetString("ad", g_sAd, sizeof(g_sAd));
    delete kv;
}

void RestartTimer()
{
    delete g_hTimer;
    g_hTimer = CreateTimer(g_cvInterval.FloatValue, Timer_Ad, _, TIMER_REPEAT | TIMER_FLAG_NO_MAPCHANGE);
}

public void OnIntervalChanged(ConVar cv, const char[] o, const char[] n)
{
    RestartTimer();
}

public Action Timer_Ad(Handle t)
{
    if (g_cvEnabled.BoolValue && g_sAd[0])
        PrintToChatAll("\x07FFD700[CustomSlop]\x01 %s", g_sAd);
    return Plugin_Continue;
}

public void OnClientPostAdminCheck(int client)
{
    if (!IsFakeClient(client) && g_sAd[0])
        CreateTimer(20.0, Timer_Hint, GetClientUserId(client), TIMER_FLAG_NO_MAPCHANGE);
}

public Action Timer_Hint(Handle t, int userid)
{
    int client = GetClientOfUserId(userid);
    if (client && IsClientInGame(client))
        PrintToChat(client, "\x07FFD700[CustomSlop]\x01 New weapons are in your loadout. If one shows as \"#TF_Default_ItemDef\", disconnect and rejoin.");
    return Plugin_Stop;
}

public Action Cmd_Reload(int client, int args)
{
    LoadToday();
    ReplyToCommand(client, "[CustomSlop] %s", g_sAd[0] ? g_sAd : "(no today.cfg)");
    return Plugin_Handled;
}

public void OnMapEnd()
{
    g_hTimer = null;   // the timer is TIMER_FLAG_NO_MAPCHANGE: it is already gone
}
