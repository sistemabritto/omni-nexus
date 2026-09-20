# Learning: OmniRoute Model Chain Architecture

## Context
During a conversation about continuing an audit and configuring Drael as priority in the OmniRoute chain, I learned key architectural details about how OmniRoute works in the EvoNexus system.

## Key Insight
The models referenced in `config/providers.json` (Britto-Core, Britto-Coding, etc.) are not direct model configurations but rather **"combos"** or named model chains defined **within the OmniRoute service itself**. 

The `providers.json` file in the evo-nexus repository is merely a **consumer** that points to the OmniRoute gateway (`http://evonexus_omniroute:20128/v1`) and uses these predefined combo names.

## Architecture Details
- **OmniRoute** is a separate Node.js gateway service (running as `diegosouzapw/omniroute` Docker image)
- It runs on the VPS (not locally in the development environment)
- Model combos are stored in OmniRoute's internal database/volume (`/app/data` mounted as `omniroute_data` volume)
- The local `providers.json` only contains references to these combo names, not their actual configurations
- To modify the model chain (e.g., add Drael as priority), one must interact with OmniRoute's API or internal configuration, not just edit local files

## Implications for Configuration
To add Drael (the drael/drael-v1 model running on drael.sh) as a priority in the OmniRoute chain:
1. Need access to OmniRoute's API (requires proper API key)
2. Need Drael's OpenAI-compatible API endpoint and key
3. Must configure Drael as a provider/model within OmniRoute's internal system
4. Then adjust the model_chain or create a new combo that prioritizes Drael

## Verification
The OmniRoute public endpoint (`omni.sistemabritto.com.br`) responds with 401 when accessed without proper API key, confirming it requires authentication for administrative actions like model configuration.

## Related Files Examined
- `config/providers.json` - shows combo references, not actual model configs
- Docker compose references to OmniRoute service
- Understanding that dashboard uses internal `http://evonexus_omniroute:20128/v1` endpoint

This learning corrects the assumption that model configuration happens in the evo-nexus repository and clarifies that OmniRoute manages its own model definitions internally.
