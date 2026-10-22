# Colab research compute

Verified September 27, 2026 using Google's official
[Colab CLI](https://github.com/googlecolab/google-colab-cli).
The local installation and Google sign-in are complete. A Tesla T4 executed
20 synthetic gradient updates, saved a checkpoint, and returned the exact
same checkpoint bytes to this Mac. The session was then terminated; usage
reported zero active assignments and zero units/hour. This checks compute and
artifact transfer, not pronunciation-model quality. No speech was uploaded.

The account displayed 300.00 units before and after this short check, at the
CLI's displayed precision. The user subsequently authorized **300 existing compute
units across this month's work**. The first real pronunciation-training pilot
remains capped at **five units**, with a shorter runtime limit and automatic
shutdown. See the [fixed pilot protocol](colab-expanded-pilot-protocol.md).

The isolated CLI executable on this Mac is
`~/.codex/integrations/colab-cli/venv/bin/colab`. Its source revision and resolved
package inventory are stored beside that environment. Authentication remains
in the CLI's private local configuration; never copy tokens into the repository,
notebooks, uploads or reports. The browser callback helper is available locally
if reauthentication is needed. The normal CLI refreshes saved credentials.

Google's [Colab MCP server](https://github.com/googlecolab/colab-mcp) is also
installed and registered with Codex as `colab`. A test established browser
connection, notebook tool discovery and notebook reading, but the bridge then
disconnected. Notebook execution through MCP was **not** verified. Use the
verified CLI for unattended work; do not depend on a browser remaining open.

## Real pronunciation pilot

The [first real speech-training pilot](colab-expanded-pilot-results.md) is now
complete. Both matched continuation arms ran two epochs on a T4; final-layer
adaptation failed the declared improvement screen. The results were downloaded
and verified, and the runtime was stopped. Colab displayed 0.03 units deducted;
budget approximately 0.09 units conservatively from the full runtime and observed
rate, because the displayed balance may lag billing. No larger run or model
promotion followed.

## Running an experiment

1. Declare the exact research question, permitted data, speaker split, source
   and checkpoint hashes, fixed training matrix, expected duration, maximum
   runtime and compute-unit budget before provisioning.
2. Read `colab usage`. Create one named session, initially requesting a T4
   unless measured memory/throughput requires another accelerator. Record the
   actual GPU and usage rate, and shorten the job if it cannot fit the budget.
3. Pin and verify the research dependencies. The setup runtime supplied Python
   3.13.15 and PyTorch 2.11.0+cu128; local experiments currently use PyTorch 2.8.0.
   Do not treat results across those environments as exact reproducibility
   without the required parity check.
4. Upload only the declared code and permitted data. Exclude credentials,
   patient recordings, unrelated workspace files and author-test recordings.
   Preserve source terms and data lineage. A mounted personal Drive is not
   required for upload/download and was not mounted during setup.
5. Run a bounded job with recoverable checkpoints. Download and hash-check
   checkpoints, predictions, logs and reports before releasing the runtime.
6. Always stop the named session, including after failure. The CLI maintains
   active sessions in the background; an idle browser is not a shutdown signal.
   Verify zero usage for the released session and record consumed units.

The setup check is retained in the ignored local
[verification record](../../research/audio-head/outputs/multiphone-20260927/colab-setup/verification.json).
No paid purchase, additional subscription or production deployment occurred.
