# WordCountBot
A Discord bot for counting how many times someone said a word. **Very much a quickie scratch project. Don't consider this "production ready" or an example of good python code :)**


## Todo

- refactor everything with a design that's been thought about for more than 10 seconds

- make storing counted messages optional, being able to replay messages is a cool feature, but 
  spam could make this too expensive to keep in memory

- store last read message timestamps so bot doesn't have to repeat work

- issue rescan on shutdown/restart??

- save state to JSON on shutdown, load saved state on start. also consider sqlite i guess
