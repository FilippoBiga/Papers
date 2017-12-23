# Papers
Python script I use to manage the papers I read.

### Features
- Keep papers and their notes organized in a folder
- Maintain a SQLite database for metadata
- Tag each paper with keywords
- Search through titles and keywords
- List all the papers in the DB
- Keep a reading status (read, unread, work in progress) for each paper


#### Initial setup
```
$ export PAPERS_DIR=~/path/to/papers/dir
$ papers init
```

#### Import a paper (and create notes.txt inside the import folder)
```
$ papers import -f reflections.pdf -t 'Reflections on Trusting Trust'
```

#### List all the papers (along with date and their reading status)
```
$ papers list -s -d
```

#### Associate a certain keyword to the last added paper
```
$ papers word -a security -p last
```

##### Search and display the papers with a certain keyword associated to them
```
$ papers search -k security
```