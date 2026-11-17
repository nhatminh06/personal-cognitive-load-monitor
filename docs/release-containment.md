# Release containment and cleanup

No executable image-release or cloud-deployment workflow is included in this candidate. A future workflow requires a separate review and explicit authorization.

If a future registry push succeeds but post-push identity, vulnerability, or signature verification fails:

1. Stop the workflow and prevent promotion or deployment of the digest.
2. Record the exact immutable registry digest, source revision, workflow run, failure, and timestamps without copying credentials into evidence.
3. Revoke or constrain release credentials if credential misuse is possible.
4. Quarantine or delete the failed digest using the registry's documented retention and deletion behavior only after an authorized operator verifies the exact target.
5. Confirm that mutable tags no longer resolve to the rejected digest; preserve the incident record.
6. Re-run source, build, vulnerability, identity, and signature qualification before any later release.

Deletion may not retract cached or already pulled content. Cleanup behavior is registry-specific and has not been tested for this candidate, so no automated cleanup command is provided.
