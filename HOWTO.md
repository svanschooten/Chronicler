# Chronicler How-To Guides

This document provides practical guides for configuring and running Chronicler in various modes.

## Setting Up Chronicler

When you run Chronicler for the first time without a configuration file, the configuration wizard will start automatically.

```bash
python -m chronicler
```

The wizard will ask you how you would like to run Chronicler.

### Running as Full Stack (Local)

1. Select option **1. Full Stack**.
2. Enter the path where you want to store your workspace (default: `~/ChroniclerWorkspace`).
3. Choose to generate or enter an API key. If you choose to enter one but leave it blank, a new key will be automatically generated for you.
4. Start the application: `python -m chronicler`.

### Running as a Server

1. Select option **3. Server**.
2. Enter the workspace path.
3. Generate or enter an API key. This key will be required by any Thin Clients or Web Clients connecting to this server.
4. Start the server: `python -m chronicler server`.

### Running as a Thin Client

1. Ensure you have a Chronicler Server running and you have its URL and API key.
2. Select option **2. Thin Client**.
3. Enter the Server URL (e.g., `http://192.168.1.10:8000`).
4. Enter the API key provided by the server (if you leave this blank, a new key will be generated, but it must match the server's key to work).
5. Start the application: `python -m chronicler`.

### Running the Web Client (Server)

1. Ensure you have a Chronicler Server running.
2. Select option **4. Web Client (Server)**.
3. Enter the Server URL and API key.
4. Start the web client server: `python -m chronicler client:web`.
5. Open your browser at `http://localhost:8080`.

## Configuration File Locations

Chronicler looks for configuration in the following locations:

1. `~/.chronicler_config.yaml` (Recommended)
2. OS-specific configuration directory (e.g., `~/.config/Chronicler/settings.yaml` on Linux).

You can manually edit these files to change your settings.

### Example `settings.yaml`

```yaml
workspace_path: /home/user/ChroniclerWorkspace
api_key: some-secret-key
server_url: null
app_name: Chronicler
```
