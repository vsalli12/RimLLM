# RimLLM

A colony diary for RimWorld 1.6, targeting .NET Framework 4.7.2.

## Diary

- Enable **Harmony** before **RimChronicle** in the mod list.
- On a new or existing colony, a diary appears beside a colonist as soon as
  the game runs. Starting colonists must first leave their arrival pods.
- There is one diary per save. Existing diaries in inventories, containers,
  other loaded maps, or caravans prevent another from appearing.
- Select a colonist, right-click the diary, and choose **Pick up Diary**.
- The right-side **Diary not assigned** alert points to an unattended diary.
- It cannot take damage, burn, or deteriorate, and stays in inventory when downed
  or automatically unloading other items. Other inventory and equipment still
  follow the game's normal rules.
- To change the chronicler, drop it from the pawn's **Gear** tab and have someone
  else pick it up. Death follows the usual inventory-drop rules.

The diary uses the custom texture in `Textures/diary.png`. Colony-wide event recording
continues even when nobody carries it. Its carrier selects the narrator; an unassigned
diary means neutral narration. LLM story generation is not implemented yet.

## Local receiver

### Local dashboard

Run `python dev/main.py`, then open **http://127.0.0.1:8766**. Stop
`host_frontend.py` first if it is already using that port. The dashboard hosts
the diary viewer at `/diary`, checks receiver/ComfyUI/Ollama status every five
seconds, and saves diary generation settings in `dev/diary_settings.json`.
Use `python dev/list_games.py` to find a recorded game ID, enter it in the
dashboard, and choose **Save & generate**. Progress and errors appear in the
terminal; the dashboard reports completion. Existing entries are skipped unless
you enable regeneration. Settings are frozen for each run; later edits apply
to the next run. Stopping the dashboard also stops its active generation.

The receiver starts and stops with the dashboard. Stop any standalone receiver
before starting the dashboard. Start Ollama and ComfyUI separately. ComfyUI is only needed for
illustrations. The dashboard itself uses Python's standard library; generation
uses the existing pipeline and its dependencies. The model and token settings
apply to diary prose; cleanup and image prompt passes retain their own settings.
The latest session and its saved ancestry are always selected automatically.
Each day uses the last non-null carrier recorded that day. All of that day's
packets remain available, including profiles before pickup, ownership changes,
and deaths recorded while the diary was unassigned. Days with no recorded
carrier still produce no diary entry. Regenerate existing entries to restore
context previously excluded by the carrier filter.
The generator can also consume saved settings with
`python dev/generate_chronicles.py --settings dev/diary_settings.json`.

Each book keeps its first recorded day's protagonist in its title (for example,
**Engie's story**), even after another carrier takes over. `book.json` stores
that identity and the opening context. Before daily generation, a separate
prologue uses the protagonist's recorded background, scenario, and map conditions
available at their first diary pickup. It appears before Day 1 and is reused on
subsequent runs, including daily regeneration. It is not added to factual story
memory. If recording began after Day 1, the earliest available carried day supplies
the opening; missing history is not invented.

Use **Night mode** on either page to switch the dashboard and diary to a dark
palette. The browser remembers the preference. In the dashboard, **Load diary
tellers** uses the entered game ID and its latest save ancestry. Select a teller,
edit their cached backstory, and click **Override diary teller personality**.
This replaces that character's backstory JSON for this game. Future generation
uses the override without another backstory LLM call; existing pages and cached
prologues stay unchanged. Overrides can be saved once an active generation finishes.

From this repository's terminal:

```powershell
.\dev\Start-Receiver.ps1
```

The launcher uses `~/miniconda3/envs/default/python.exe` when available, otherwise
Python on PATH. Alternatively:

```powershell
conda activate default
python -X utf8 dev/receiver.py
```

Restart RimWorld after building, load a colony and unpause. The terminal should
print JSON events. The receiver listens only on `127.0.0.1:8765`, requires no pip
packages, and stores received events in `dev/events.sqlite3`. Stop with Ctrl+C.
See [the event protocol](dev/PROTOCOL.md) for event types and limitations.

Quick in-game test:

1. Load/unpause: expect `session.started`, profiles and `session.snapshot`.
2. Pick up/drop the Diary: expect `diary.owner_changed` with a pawn ID or null.
3. Leave it unassigned: social and colony events should continue arriving.
4. Stop the receiver, play briefly, then restart it: buffered events should arrive.
5. Reload a save: expect a new session ID linked to that save's checkpoint.
6. Order a colonist to mine or construct, then switch tasks: expect
   `pawn.job_changed` with the previous/current job and target. Continuing the same
   job should not repeat the event. Resting and other job types are included too.

The receiver and C# transport have automated tests; game event hooks still need
in-game verification. Do not run transport tests while the receiver is using port 8765.

## In-game verification

To generate a test LLM prompt from **all day 1 events**, without calling an LLM:

```powershell
conda activate default
python dev/build_day_prompt.py
```

Open `dev/day1_prompt.json`. Each session has its own `prompt.system` instructions
and structured `prompt.user` context (serialize the latter as JSON for an LLM), with readable
event summaries, readable emotional context, pawn biographies and narrator identity. Reloaded
sessions are kept separate to avoid mixing alternate histories. This first pass
does not rank or discard day-1 events; the output may be large. The day is hardcoded
as `DAY = 1` in the script. Generated prompts are ignored by Git.

Active cast membership requires presence on a map/caravan or participation in an
actual event, not just `is_colonist`. Unplaced older profiles are labelled
background-only; a pawn who dies during play remains part of the story. Profiles
and narrator state are reset per session. The prompt requests prose rather than
JSON analysis. To send it to your existing local model:

```powershell
python dev/ollama_inference.py
```

This uses the generated system instructions and only the first session; select
another with `--session 1` (zero-based). It performs an LLM call only when run.

After building, restart RimWorld and check these on a test save:

1. Load a colony: exactly one diary appears and the alert is visible.
2. Pick it up: it appears in Gear, and the alert disappears.
3. Save and reload: the same pawn still has it and no second diary appears.
4. Down its carrier using Development mode: the diary stays in inventory;
   ordinary equipment still drops. Recover the pawn and confirm it remains held.
5. Drop it manually, then assign a different pawn: the alert appears and clears.
6. Try fire/explosion damage on the loose diary: it remains intact.
7. Take the carrier on a caravan and return: no replacement diary appears,
   and normal inventory unloading leaves the diary in their inventory.
8. Kill the carrier in a test save: the diary can be recovered.

These require a running game; a successful build alone does not verify them.

## Build and test

Install the .NET 10 SDK, Microsoft's C# extension in VS Code, and the Harmony
Workshop mod. Build with
**Ctrl+Shift+B**, or run:

```powershell
dotnet build --configuration Release
```

The output is `Assemblies/RimChronicle.dll`. Framework reference assemblies are
restored from NuGet automatically. Game DLLs are referenced from
`C:\Program Files (x86)\Steam\steamapps\common\RimWorld` and are not copied into
the mod. To use a different installation:

```powershell
dotnet build --configuration Release '-p:RimWorldDir=D:\Games\RimWorld'
```

To make this checkout available in the game's Mods menu, run this once in
PowerShell (an elevated terminal may be needed for Program Files):

```powershell
New-Item -ItemType Junction -Path 'C:\Program Files (x86)\Steam\steamapps\common\RimWorld\Mods\RimChronicle' -Target 'C:\Users\vilia\Documents\GitHub\RimChronicle'
```

If that destination already exists, inspect it before proceeding. Alternatively,
copy `About` and `Assemblies` into a new `Mods\RimChronicle` folder, and copy updated
assemblies after builds.
Also copy `Defs` and `Textures` when installing this version manually.

Enable **RimChronicle** in the Mods menu and restart the game. Enable Development
mode in Options and check the debug log for
`[RimChronicle] Mod loaded successfully.` Restart the game after C# changes.
Harmony is referenced from its Steam Workshop `Current/Assemblies/0Harmony.dll`;
it is not bundled into this mod. For a different location, pass
`'-p:HarmonyDll=D:\Mods\Harmony\Current\Assemblies\0Harmony.dll'` to the build.
The author and package ID in `About/About.xml` are starter values;
choose your final identity before publishing.

## Original template reference

A template for creating RimWorld mods.

## File Structure Overview

RimWorld mods are folders which contain subfolders and files with specific names.

- `/About` contains meta information about the mod.
- `/Assemblies` contains C# assemblies for the mod.
- `/Defs` contains XML files with definitions for each thing added by the mod.
- `/Languages` contains translation data for the mod.
- `/Patches` contains XML files with modifications to the definitions of things added by other mods.
- `/Sounds` contains audio files supplied by the mod.
- `/Textures` contains image files supplied by the mod.

## Multi-Version Mods

Starting from a mod's root directory, RimWorld checks a sequence of subfolders in order and loads files from all of them:

- `/1.6` (skipped if any folder above was found)
- `/1.5` (skipped if any folder above was found)
- `/1.4` (skipped if any folder above was found)
- `/1.3` (skipped if any folder above was found)
- `/1.2` (skipped if any folder above was found)
- `/1.1` (skipped if any folder above was found)
- `/1.0` (skipped if any folder above was found)
- `/Common` (always checked)
- `/` (always checked)

If the same file name is present in several of these folders, the first one checked will take precedence and the others will be ignored.

The `About` folder should always be in the mod's root directory. It cannot differ between game versions.

When sharing files between versions, the `Common` folder should be used.

To gain finer control over how mod files are loaded, you can make a file called `LoadFolders.xml` in the mod's root directory. For example:

```xml
<?xml version="1.0" encoding="UTF-8" ?>

<loadFolders>
	<v1.1>
		<li>Common</li>
		<li>1.1</li>
	</v1.1>
	<v1.2>
		<li>Common</li>
		<li>1.2</li>
		<!-- IfModActive and IfModNotActive can contain comma-separated (treated like an OR operator) package IDs of mods. The folder will only be loaded if the condition is met. -->
		<li IfModActive="Ludeon.RimWorld.Royalty">RoyaltySpecific</li>
	</v1.2>
	<v1.3>
		<li>Common</li>
		<li>1.3</li>
		<li IfModActive="Ludeon.RimWorld.Ideology,Ludeon.RimWorld.Royalty">AnyExpansions</li>
		<li IfModNotActive="Ludeon.RimWorld.Ideology">NoIdeology</li>
	</v1.3>
</loadFolders>
```

When using the format above, the last folder in the list takes precedence.

RimWorld version 1.0 does not support the load folder system, but it does support loading `Defs`, `Patches`, and `Assemblies` from `/1.0`. It will always look for `Textures`, `Translations`, and `Sounds` in the mod's root directory. If you create `/1.0`, RimWorld version 1.0 will not look for `Defs`, `Patches`, and `Assemblies` in the root directory.

## Documentation

RimWorld is not well-documented. When RimWorld is downloaded through Steam on Windows, the default directory of the `RimWorld` folder is `C:\Program Files (x86)\Steam\steamapps\common\RimWorld`. For XML documentation, `RimWorld/Data` and `RimWorld/Source` will contain a variety of examples from the base game. For C# documentation, the relevant code can be decompiled (such as with [ILSpy](https://github.com/icsharpcode/ILSpy)) from `RimWorld/RimWorld*_Data/Managed` (especially `Assembly-CSharp.dll` and `UnityEngine.CoreModule.dll`). It is a good idea to find a mod which does something similar to what you're attempting to do and look at the code for that mod. There is a modding tutorial available on the [RimWorld Wiki](https://rimworldwiki.com/wiki/Modding). A list of tutorials and resources is available on [spdskatr's website](https://spdskatr.github.io/RWModdingResources/). If you can't find something, ask for help on the [Ludeon Forums](https://ludeon.com/forums/).

## Harmony

The following table lists the recommended [Harmony](https://github.com/pardeike/Harmony) version for each version of RimWorld. The column titled "Include Harmony" includes a value of "Yes" for versions of RimWorld that should include `0Harmony.dll` in their `Assemblies` folder, or "No" for versions of RimWorld that should depend on [the Harmony mod](https://github.com/pardeike/HarmonyRimWorld) instead.

| RimWorld | Harmony     | .NET Framework | Include Harmony |
| -------- | ----------- | -------------- | --------------- |
| 1.0      | 1.2.0.1     | 3.5            | Yes             |
| 1.1      | 2.2.0.0[^1] | 4.7.2          | Yes             |
| 1.2      | 2.2.2.0     | 4.7.2          | No              |
| 1.3      | 2.2.2.0     | 4.7.2          | No              |
| 1.4      | 2.2.2.0     | 4.7.2          | No              |
| 1.5      | 2.3.3.0     | 4.7.2          | No              |
| 1.6      | 2.4.1.0[^2] | 4.7.2          | No              |

[^1]: There is conflicting information about which version of Harmony should be used with RimWorld version 1.1. [According to Harmony's developer](https://github.com/pardeike/HarmonyRimWorld/issues/39), you should use version 1.2.0.1, but it was standard practice at the time of its release to use version 2.x, so it's probably best to use version 2.2.2.0.
[^2]: For the latest version of RimWorld, check [the RimWorld mod's GitHub repository](https://github.com/pardeike/HarmonyRimWorld) to ensure that the proper version is being used.


### Diary scribbles (development)

Run local Ollama and ComfyUI at `127.0.0.1:8188`. Daily generation now saves the
entry first, then calls `RAG_main.generate_image_prompt` and sends the scene text
to node 130 (`inputs.value`) of `dev/ZIT_scribble_generate.json`. Node 131 retains
the workflow's pencil-style prefix; node 132 supplies the saved image.
Set `GENERATE_SCRIBBLES = False` in `dev/generate_chronicles.py` for text only.

To illustrate existing entries without regenerating their prose:

```powershell
python dev/image_generation.py dev/chronicles/<game-id>/<session-id>
```

A single `day001.json` path also works. Add `--force` to regenerate an illustration.
Otherwise matching entry text and workflow reuse the saved scene prompt and PNG.
The `.scribble.json` sidecar stores the scene prompt and cache metadata, and the
entry JSON links its image. Image failures leave the diary intact and can be
retried with the same command. ComfyUI output is downloaded through its API, so
no local ComfyUI input/output directory configuration is needed.

Restart `dev/host_frontend.py` after updating its code, then refresh the diary.
Available illustrations appear beneath each entry; older entries without images
remain readable.
