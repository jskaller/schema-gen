# schema-gen

This repository is managed using a *patch drop* workflow:
I (the assistant) send numbered `.patch` files; you apply them locally
and push to GitHub.

## Apply a patch

1. Save the patch file into the repo root (e.g. `0001-chore-seed-repo.patch`).
2. If this is the very first commit in a brand‑new repo, create an empty
   initial commit so `git am` can run:

   ```bash
   git commit --allow-empty -m "chore: repo init"
   ```

3. Apply the patch (creates a proper commit with metadata):

   ```bash
   git am 0001-chore-seed-repo.patch
   ```

4. If you hit conflicts:
   - Fix files, `git add -A`
   - Continue: `git am --continue`
   - Or abort: `git am --abort`

5. Push to GitHub:

   ```bash
   git push -u origin HEAD:main
   ```

## Next
We’ll iterate with small, focused patches that add code and tests.

