# Important Use Cases

This document summarizes important use cases for testing whether the wrapper works.

## Normal messages

1. User message sent from UI should be sent and submitted to terminal 
2. User message sent from terminal should be displayed in UI.
3. Agent message from terminal should be displayed in UI.
4. No duplicate of user or agent messages

## Push Notifications

5. Push notifications should be sent to user when agent completes a task, not while it is running.

## Permission Requests

6. Permission request response options should be properly displayed in UI.
7. Selecting an option of permission request in UI should be sent to terminal.
8. Selecting options like "No" of permission request response options, it should be able to send new messages from UI to terminal. 

## Control Messages

e.g. interruption, change permission mode, change model, change agent, etc.  

9. Interrupt the agent from UI while it is busy.
10. User messages sent while agent is busy should be handled directly, control messages are processed, other messages are send to the terminal directly. 
11. Permission mode changes in terminal is reflected in UI with a response.
12. Permission mode changes from UI should be reflected in terminal.

## Close Terminal

13. Closing the terminal should update the session status.