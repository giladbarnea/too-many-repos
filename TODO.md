# Features
## Logic
- [ ] `tmr ignore`
  - [ ] `tmr ignore <path>`
  - [ ] `tmr ignore <string>`
  - [ ] `tmr ignore show`
- [ ] `tmr -u`    # don't honor .tmrignore file
  - [ ] `tmr -u <path / string>`    # don't ignore specific entry
- [x] `--difftool code`

## `.tmrignore`
- [ ] support for env vars e.g. $HOME/.gitignore
- [ ] support for ignoring by repo url
- [ ] support for # -i or # --case-insensitive at line end
- [x] support for #comments

## `.tmrrc`
- [ ] `diff` rules
  - [ ] ignore difference in line order (think .ignore files)
  - [ ] `diff gist` rules
    - [ ] "count as same when:"
      - [ ] local is subset
  - [x] ignore #comments

# Improvements
## Gists
- [ ] option to edit gist if diff exists or "upload" local (after showing diff) | p2

## Repos
- [ ] before pull
  - [ ] suggest to show diff
  - [ ] show upstream name if exists
- [ ] after pull from upstream, suggest to git push to origin
- [ ] if can be safely `gacp`ed, suggest to do it
  - [ ] when's safe? 
        Your branch is up to date with 'origin/master'
        Changes not staged for commit:
        no changes added to commit (use "git add" and/or "git commit -a")
- [ ] bold `ahead` in "but your branch is ahead of upstream by 3 commits"

# Bugs
## Gists
- [ ] when a gist includes several files (like micro settings) | p1
- [ ] gists are downloaded even if ignored | p1
- [ ] gist tmp file includes gist description
- [ ] put the newer (gist or local) on the right (green) | p2

## Repos 
- [ ] repos are checked for .git dir size even if ignored

## `.tmrignore`
- [ ] only full gist ids are matched. should match first 4 chars
# Thoughts
- If upstream != origin, and tracking == origin/*, warn? warning rules in .tmrrc?
- "Your branch is based on 'origin/master', but the upstream is gone.
  (use "git branch --unset-upstream" to fixup)" (`attrs`)
