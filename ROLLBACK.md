# 🛟 ROLLBACK — How to bring the whole Trader back

This app is version-controlled with git, so **every change is reversible** and you
can always return to a known-good version — locally and on Render. This file is
the safety net: if anything ever gets worse or stops working, use it.

> Rule we both follow: **nothing is ever changed in a way that removes your
> ability to go back.** No history is rewritten, no force-pushes, every change is
> a normal commit you can undo.

---

## 🏷️ Named restore points (safe versions to return to)

| Tag | What it is |
|-----|-----------|
| `restore-baseline-20260728` | The app **before** this week's changes (original working state). |
| `restore-20260730` | Snapshot taken 2026-07-30 (includes the week's fixes). |

New restore tags get added over time (newest = most recent safe point). List them:

```bash
git tag --list "restore-*"
```

---

## ↩️ Roll the LIVE (Render) app back to a restore point

Render auto-deploys whatever is on the `main` branch on GitHub. To go back:

```bash
git checkout main
git reset --hard restore-baseline-20260728   # or any restore-* tag
git push --force-with-lease origin main
```

Render redeploys the old version automatically (~3–5 min). Your keys/settings on
Render are unaffected. *(force-with-lease is the safe form of force-push; it
refuses if someone else pushed in the meantime.)*

> Prefer not to rewrite `main`? Use a **revert** instead — it undoes changes by
> adding a new commit, so nothing is lost:
> ```bash
> git revert --no-commit restore-20260730..main && git commit -m "Roll back to 20260730" && git push
> ```

---

## 💻 Roll your LOCAL copy back

```bash
git stash               # set aside any uncommitted edits (recover later with: git stash pop)
git checkout restore-baseline-20260728   # look at the old version safely
# happy? make it your working version:
git checkout -B main restore-baseline-20260728
```

---

## 🔎 See what changed before deciding

```bash
git log --oneline restore-baseline-20260728..main      # commits added since baseline
git diff restore-baseline-20260728 main -- <file>       # exact changes to a file
```

---

## 🧰 Extra safety nets already in place

- **Automatic state backups** (`BACKUP_ENABLED=true`) snapshot license/settings/state
  every 15 min, keeping 96 (24 h) — see the `snapshots/` folder / backup logs.
- **Render keeps the previous version live** if a new deploy fails its health check,
  so a bad deploy can't take the site down.

If you're ever unsure, ask and I'll walk you through the exact rollback for your
situation — and I'll always tell you before and after I change anything.
