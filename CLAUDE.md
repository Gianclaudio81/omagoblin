# OmaGoblin maintenance

This repository distributes only an Omarchy shell plugin. Keep desktop configuration, credentials, usage records and session transcripts out of Git.

Preserve the upstream MIT notice and attribution. Depend on Omarchy's existing collectors rather than embedding authentication or billing implementations.

Plugin identity: `tod.omagoblin`. Keep manifest, panel module and IPC target consistent. Do not change the shared Omarchy usage-data directory when renaming the plugin.

Validate with `omarchy plugin validate .` and `bash -n active-model.sh`. Use synthetic session records when testing the model helper.
