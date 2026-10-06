# RimLLM

RimLLM is a RimWorld 1.6 mod and local companion app that records colony events and turns them into a narrator-led diary using a local language model. The goal is to retain mementos of RimWorld saves, a feature that more or less is missing from the game. 

The diary teller is aware of the colony history, day's events and social, health and mood records. The diary teller is fleshed out to help personalize the story. 

The LLM and the optional image generation runs locally. A GPU is needed with optimally 16GB VRAM. 

## Requirements

- RimWorld 1.6 and the [Harmony](https://steamcommunity.com/sharedfiles/filedetails/?id=2009463077) mod
- Python 3.10 or newer and the packages in `requirements.txt`
- [Ollama](https://ollama.com/) with a chat model for diary generation
  * gemma3:12b is the recommended model to use
- ComfyUI is optional and only needed for diary illustrations

## Installation

1. Clone or download this repository into RimWorld's `Mods` folder. The prebuilt `Assemblies/RimLLM.dll` is included.
2. Install the Python packages with `python -m pip install -r requirements.txt`.
3. Enable Harmony and RimLLM in RimWorld, with Harmony above RimLLM in the mod list.

## Use

1. Start dev/main.py. This will start the local server to which RimWorld sends event data, and a dashboard.
2. Load a colony with RimLLM mod enabled. To ensure the mod works, monitor the python console which should start printing out event data.
3. Ensure that the diary is picked up by someone.
4. Generate the diary manually at any point in dashboard. 

To rebuild after changing the C# source, install the .NET 10 SDK and run `dotnet build --configuration Release`. Set `RimWorldDir` or `HarmonyDll` if those installations are outside their default Steam locations.
