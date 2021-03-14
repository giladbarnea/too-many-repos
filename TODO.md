# .tmrrc
# .tmrignore
- [ ] support for #comments

# features
## code
- [ ] `--difftool code`

## .tmrignore
- [ ] support for env vars e.g. $HOME/.gitignore

## .tmrrc
- [ ] `diff` rules
  - [ ] ignore diff in line order (think .ignore files)
  - [ ] ignore comments
  - [ ] `diff gist` rules
    - [ ] "count as same when:"
      - [ ] local is subset



# improvements
## gists
- [ ] option to edit gist if diff exists or "upload" local (after showing diff) | p2

## repos
- [ ] before pull, suggest to show diff
- [ ] after pull from upstream, suggest to git push to origin
- [ ] if can be safely `gacp`ed, suggest to do it
  - [ ] when's safe? 
        Your branch is up to date with 'origin/master'
        Changes not staged for commit:
        no changes added to commit (use "git add" and/or "git commit -a")
- [ ] bold `ahead` in "but your branch is ahead of upstream by 3 commits"

# bugs
- [ ] when a gist includes several files (like micro settings) | p1
- [ ] gist tmp file includes gist description