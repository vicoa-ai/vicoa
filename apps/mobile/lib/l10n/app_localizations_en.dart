// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get tasksAllProjects => 'All projects';

  @override
  String get tasksCancel => 'Cancel';

  @override
  String get tasksCouldNotLoad => 'Couldn\'t load tasks';

  @override
  String get tasksCreate => 'Create';

  @override
  String get tasksDelete => 'Delete';

  @override
  String get tasksDeleteConfirmBody =>
      'This task will be permanently deleted. This can\'t be undone.';

  @override
  String get tasksDeleteConfirmTitle => 'Delete task?';

  @override
  String get tasksDescriptionFieldLabel => 'DESCRIPTION';

  @override
  String get tasksDescriptionPlaceholder => 'Add details…';

  @override
  String get tasksEdit => 'Edit';

  @override
  String get tasksEditTask => 'Edit task';

  @override
  String get tasksLabelsFieldLabel => 'LABELS';

  @override
  String get tasksNewTask => 'New task';

  @override
  String get tasksDisplay => 'Display';

  @override
  String get tasksInbox => 'Inbox';

  @override
  String get tasksLabelsButton => 'Labels';

  @override
  String get tasksPropPriority => 'Priority';

  @override
  String get tasksPropProject => 'Project';

  @override
  String get tasksPropStatus => 'Status';

  @override
  String get tasksNoTasksSubtitle =>
      'Create a task to plan work you can hand to an agent.';

  @override
  String get tasksNoTasksTitle => 'No tasks yet';

  @override
  String get tasksPriorityFieldLabel => 'PRIORITY';

  @override
  String get tasksPriorityHigh => 'High';

  @override
  String get tasksPriorityLow => 'Low';

  @override
  String get tasksPriorityMedium => 'Medium';

  @override
  String get tasksPriorityNone => 'No priority';

  @override
  String get tasksPriorityUrgent => 'Urgent';

  @override
  String get tasksProjectFieldLabel => 'PROJECT';

  @override
  String get tasksPullToRefresh => 'Pull to refresh';

  @override
  String get tasksSave => 'Save';

  @override
  String get tasksSaveFailed => 'Couldn\'t save task. Please try again.';

  @override
  String get tasksStartSession => 'Start session';

  @override
  String get tasksSubtasks => 'Sub-tasks';

  @override
  String get tasksStatusBacklog => 'Backlog';

  @override
  String get tasksStatusBlocked => 'Blocked';

  @override
  String get tasksStatusCancelled => 'Cancelled';

  @override
  String get tasksStatusDone => 'Done';

  @override
  String get tasksStatusFieldLabel => 'STATUS';

  @override
  String get tasksStatusInProgress => 'In Progress';

  @override
  String get tasksStatusInReview => 'In Review';

  @override
  String get tasksStatusTodo => 'Todo';

  @override
  String get tasksTaskDeleted => 'Task deleted';

  @override
  String get tasksTitle => 'Tasks';

  @override
  String get tasksTitleFieldLabel => 'TITLE';

  @override
  String get tasksTitlePlaceholder => 'What needs to be done?';

  @override
  String get tasksTitleRequired => 'Title is required';

  @override
  String get accountCautionZone => 'CAUTION ZONE';

  @override
  String get accountDeleteAccount => 'Delete Account';

  @override
  String get accountDeleteDialogBody =>
      'All your data will be permanently deleted. Are you sure to proceed?';

  @override
  String get accountDeleteDialogTitle => 'Delete Account?';

  @override
  String get accountEmail => 'Email';

  @override
  String get accountLogOut => 'Log Out';

  @override
  String get accountName => 'Name';

  @override
  String get accountNameHint => 'Guest';

  @override
  String get accountRegistration => 'Registration';

  @override
  String get accountTitle => 'Account';

  @override
  String get addToChatChooseFiles => 'Files';

  @override
  String get addToChatCommands => 'Commands';

  @override
  String get addToChatPhotoLibrary => 'Photo';

  @override
  String get addToChatSkillsOrCommands => 'Skills or Commands';

  @override
  String get addToChatTakePhoto => 'Camera';

  @override
  String agentCatalogReasoningLabel(Object label) {
    return 'Reasoning - $label';
  }

  @override
  String agentCatalogThinkingLabel(Object label) {
    return 'Thinking - $label';
  }

  @override
  String get agentChatAddToChat => 'Add to chat';

  @override
  String get agentChatAgentMode => 'Agent Mode';

  @override
  String get agentChatCancelQueuedMessageTooltip => 'Cancel message';

  @override
  String get agentChatRevertQueuedMessageTooltip => 'Edit in input';

  @override
  String get agentChatCancelledLabel => 'Cancelled';

  @override
  String get agentChatCloseFailed =>
      'Failed to archive session. Please try again.';

  @override
  String agentChatCopiedToClipboard(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Copied $count messages to clipboard',
      one: 'Copied 1 message to clipboard',
    );
    return '$_temp0';
  }

  @override
  String get agentChatCopyFailed => 'Failed to copy messages';

  @override
  String get agentChatCopyResponse => 'Copy response';

  @override
  String get agentChatDeleteFailed =>
      'Failed to delete session. Please try again.';

  @override
  String get agentChatErrorLoadingMessages => 'Error Loading Messages';

  @override
  String get agentChatInitFailed => 'Failed to initialize chat';

  @override
  String get agentChatMentionFiles => 'Mention files';

  @override
  String agentChatNewMessagesCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count messages',
      one: '$count message',
    );
    return '$_temp0';
  }

  @override
  String get agentChatNoMessagesSelected => 'No messages selected';

  @override
  String get agentChatNoMessagesToShare => 'No messages to share';

  @override
  String get agentChatPermissionMode => 'Permission Mode';

  @override
  String get agentChatPinFailed => 'Couldn\'t pin session';

  @override
  String agentChatQueuedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count queued',
      one: '1 queued',
    );
    return '$_temp0';
  }

  @override
  String get agentChatQueuedLabel => 'Queued';

  @override
  String get agentChatQueuedSheetTitle => 'Queued messages';

  @override
  String get agentChatRenameFailed =>
      'Failed to rename session. Please try again.';

  @override
  String get agentChatSessionReady => 'Session ready';

  @override
  String get agentChatSessionRenamed => 'Session renamed successfully';

  @override
  String get agentChatSessionTitle => 'Session';

  @override
  String get agentChatShareFailed => 'Failed to share messages';

  @override
  String get agentChatShareResponse => 'Share response';

  @override
  String get agentChatShowSlashCommands => 'Show slash commands';

  @override
  String get agentChatStartingYourSession => 'Starting your session';

  @override
  String get agentChatThinking => 'Thinking';

  @override
  String get agentChatThinkingOff => 'Off';

  @override
  String get agentChatThinkingOn => 'On';

  @override
  String get agentChatTranscribing => 'Transcribing...';

  @override
  String get agentChatUnexpectedError => 'An unexpected error occurred';

  @override
  String get agentChatUnpinFailed => 'Couldn\'t unpin session';

  @override
  String get agentChatWaitingForMessages => 'Waiting for messages';

  @override
  String get agentConfigAgent => 'Agent';

  @override
  String agentConfigBetaLabel(Object label) {
    return '$label (Beta)';
  }

  @override
  String get agentConfigMode => 'Mode';

  @override
  String get agentConfigModel => 'Model';

  @override
  String get agentConfigNotInstalled => 'Not installed';

  @override
  String agentConfigNotInstalledPrefix(Object label) {
    return '$label is not installed on this machine. Install it, then restart ';
  }

  @override
  String get agentConfigNotInstalledSuffix => ' to use it.';

  @override
  String get agentConfigPanelAgent => 'Agent';

  @override
  String get agentConfigPanelMode => 'Mode';

  @override
  String get agentConfigPanelModel => 'Model';

  @override
  String get agentConfigPanelPermission => 'Permission';

  @override
  String get agentConfigPanelReasoning => 'Reasoning';

  @override
  String get agentConfigPanelThinking => 'Thinking';

  @override
  String get agentConfigPanelUnknownAgent =>
      'Unknown agent — update the app to configure this.';

  @override
  String get agentConfigPermission => 'Permission';

  @override
  String get agentConfigReasoningEffort => 'Reasoning Effort';

  @override
  String get agentConfigThinkingEffort => 'Thinking Effort';

  @override
  String get agentConfigUnknownAgent =>
      'Unknown agent — update the app to configure this.';

  @override
  String get appLanguageTitle => 'Language';

  @override
  String get appearanceChat => 'Chat';

  @override
  String get appearanceCodeBlock => 'Code Block';

  @override
  String get appearanceCollapseLongCode => 'Collapse Long Code';

  @override
  String get appearanceCollapseToolCalls => 'Collapse Tool Calls';

  @override
  String get appearanceDarkMode => 'Dark Mode';

  @override
  String get appearanceLanguage => 'Language';

  @override
  String get appearanceLinesBeforeCollapsing => 'Lines before collapsing';

  @override
  String get appearanceShowFilter => 'Show Filter';

  @override
  String get appearanceShowLivePreview => 'Show Live Preview';

  @override
  String get appearanceTitle => 'Appearance';

  @override
  String get askUserQuestionPanelCancelling => 'Cancelling...';

  @override
  String askUserQuestionPanelQuestionNumber(Object number) {
    return 'Question $number';
  }

  @override
  String get askUserQuestionPanelSubmit => 'Submit';

  @override
  String get askUserQuestionPanelSubmitting => 'Submitting...';

  @override
  String get askUserQuestionPanelTypeSomething => 'Type something';

  @override
  String get askUserQuestionPanelTypeYourAnswer => 'Type your answer';

  @override
  String get authEmailChangeConfirmationSent =>
      'Email change confirmation email sent';

  @override
  String get authOptionsAndConnector => ' and ';

  @override
  String get authOptionsContinueWithApple => 'Continue with Apple';

  @override
  String get authOptionsContinueWithEmail => 'Continue with Email';

  @override
  String get authOptionsContinueWithGoogle => 'Continue with Google';

  @override
  String get authOptionsLegalPrefix => 'By continuing, you agree to the\n';

  @override
  String get authOptionsPrivacyPolicy => 'privacy policy';

  @override
  String get authOptionsSubtitle =>
      'Run a team of coding agents from your phone';

  @override
  String get authOptionsTermsOfUse => 'terms of use';

  @override
  String get authOptionsTitle => 'Let\'s Get Started';

  @override
  String get billingXNoOffering => 'No offering available';

  @override
  String billingXPaywallLoadError(Object error) {
    return 'Error loading paywall: $error';
  }

  @override
  String get chatErrorLoadMessagesFailed =>
      'Failed to load messages. Please check your connection.';

  @override
  String get chatInputAddToChat => 'Add to chat';

  @override
  String get chatInputBrowseFiles => 'Browse files';

  @override
  String get chatInputCliOutdated =>
      'Vicoa CLI could be outdated. Upgrade it to access files and changes.';

  @override
  String get chatInputModelConfig => 'Model Config';

  @override
  String get chatInputOpenWebPreview => 'Open web preview';

  @override
  String get chatInputPlaceholder =>
      'Type messages, @files, /skills or commands';

  @override
  String get chatInputSessionConfig => 'Session Config';

  @override
  String get chatInputSessionEnded => 'Session archived. Chat is closed here';

  @override
  String get chatInputSessionReadOnly =>
      'Session is archived. Configs are read-only.';

  @override
  String get chatInputStopTask => 'Stop current task';

  @override
  String get chatOptionsInfo => 'Info';

  @override
  String get chatOptionsPin => 'Pin';

  @override
  String get chatOptionsRename => 'Rename';

  @override
  String get chatOptionsUnpin => 'Unpin';

  @override
  String get commonBack => 'Back';

  @override
  String get commonCancel => 'Cancel';

  @override
  String get commonClose => 'Close';

  @override
  String get commonConfirm => 'Confirm';

  @override
  String get commonContinue => 'Continue';

  @override
  String get commonCopied => 'Copied';

  @override
  String get commonCopy => 'Copy';

  @override
  String get commonDelete => 'Delete';

  @override
  String get commonDone => 'Done';

  @override
  String get commonEdit => 'Edit';

  @override
  String get commonError => 'Error';

  @override
  String get commonLoading => 'Loading…';

  @override
  String get commonNext => 'Next';

  @override
  String get commonNo => 'No';

  @override
  String get commonOk => 'OK';

  @override
  String get commonRemove => 'Remove';

  @override
  String get commonRetry => 'Retry';

  @override
  String get commonSave => 'Save';

  @override
  String get commonSearch => 'Search';

  @override
  String get commonSettings => 'Settings';

  @override
  String get commonShare => 'Share';

  @override
  String get commonSignIn => 'Sign In';

  @override
  String get commonSignOut => 'Sign Out';

  @override
  String get commonSignUp => 'Sign Up';

  @override
  String get commonSkip => 'Skip';

  @override
  String get commonYes => 'Yes';

  @override
  String get configureSetupConfiguringBest => 'Your AI agent\nis almost ready';

  @override
  String get configureSetupJustAMoment => 'Just a moment...';

  @override
  String get configureSetupSocialProof =>
      'People who use Vicoa have built faster with \nAI coding agents anywhere they go.';

  @override
  String get confirmDialogAreYouSure => 'Are you sure?';

  @override
  String get confirmRatingBody =>
      'Thank you for supporting us! \n\nIf you\'ve gave us a happy 5 stars, tap the button below to claim your free messages.';

  @override
  String get confirmRatingDoneButton => 'I Have Done It';

  @override
  String get confirmRatingGiftButton => 'Continue to Use';

  @override
  String get confirmRatingGiftText => 'Yay! You got 50 free messages!';

  @override
  String get confirmRatingTitle => 'Give us a Happy 5 Stars!';

  @override
  String get connectComputerLinkCopied => 'Link copied';

  @override
  String get connectComputerLoginSameAccount =>
      'Download the desktop app and sign in with the same account. Your computer connects automatically.';

  @override
  String get connectComputerTitle => 'Connect Your Computer';

  @override
  String get connectComputerViewDocs => 'View full documentation';

  @override
  String get credtiHistoryTitle => 'Credit History';

  @override
  String get dateRangeXApply => 'Apply';

  @override
  String get dateRangeXEndDate => 'End Date';

  @override
  String get dateRangeXStartDate => 'Start Date';

  @override
  String get dateRangeXTitle => 'Custom Date Range';

  @override
  String get dateRangeXWeekdayFri => 'Fri';

  @override
  String get dateRangeXWeekdayMon => 'Mon';

  @override
  String get dateRangeXWeekdaySat => 'Sat';

  @override
  String get dateRangeXWeekdaySun => 'Sun';

  @override
  String get dateRangeXWeekdayThu => 'Thu';

  @override
  String get dateRangeXWeekdayTue => 'Tue';

  @override
  String get dateRangeXWeekdayWed => 'Wed';

  @override
  String get dateToday => 'Today';

  @override
  String get dateYesterday => 'Yesterday';

  @override
  String get directoryPickerRecent => 'Recent';

  @override
  String get directoryPickerWorkingDirectory => 'Working Directory';

  @override
  String get errorStateDisplaySignInAgain => 'Sign In Again';

  @override
  String get errorStateDisplayTryAgain => 'Try Again';

  @override
  String get errorStateDisplayUnexpectedError => 'An unexpected error occurred';

  @override
  String get fileViewerXAddToContext => 'Add to context';

  @override
  String fileViewerXBinaryFile(Object size) {
    return 'Binary file ($size)';
  }

  @override
  String get fileViewerXDetailNotDownloaded => 'file is not downloaded';

  @override
  String get fileViewerXDetailOutdated => 'file could be outdated';

  @override
  String fileViewerXErrDefault(Object code) {
    return 'Couldn’t load this file ($code).';
  }

  @override
  String get fileViewerXErrMachineOffline => 'Machine is offline.';

  @override
  String get fileViewerXErrNoHandler =>
      'Update the daemon on this machine — older version doesn’t support file viewing.';

  @override
  String get fileViewerXErrNotAFile => 'Not a file.';

  @override
  String get fileViewerXErrOutsideProject => 'Path is outside the project.';

  @override
  String get fileViewerXErrPathNotFound => 'This file no longer exists.';

  @override
  String get fileViewerXErrPermissionDenied => 'Permission denied.';

  @override
  String get fileViewerXErrTimeout => 'The machine took too long to respond.';

  @override
  String get fileViewerXFileNotDownloaded =>
      'File not downloaded on this device.';

  @override
  String get fileViewerXImageTooLarge =>
      'Image too large to preview on mobile.';

  @override
  String get fileViewerXPreviewNotAvailable => 'Preview not available.';

  @override
  String get fileViewerXReconnectToView => 'Reconnect the machine to view it.';

  @override
  String get fileViewerXRefresh => 'Refresh';

  @override
  String fileViewerXShowingFirstPortion(Object size) {
    return 'Showing first portion of $size. Open on desktop to see the rest.';
  }

  @override
  String filesGitXBinaryFileChanged(Object size) {
    return 'Binary file changed · $size';
  }

  @override
  String get filesGitXCollapseAllTooltip => 'Collapse all';

  @override
  String filesGitXCouldntLoadDiff(Object code) {
    return 'Couldn’t load diff — $code';
  }

  @override
  String get filesGitXCouldntLoadStatus => 'Couldn’t load status';

  @override
  String filesGitXDetachedAt(Object branch) {
    return '(detached at $branch)';
  }

  @override
  String get filesGitXDiffTruncated =>
      'Diff truncated — open on desktop for the rest.';

  @override
  String get filesGitXExpandAllTooltip => 'Expand all';

  @override
  String get filesGitXHideWhitespaceTooltip => 'Hide whitespace';

  @override
  String get filesGitXNoChangesVsHead => 'No changes vs HEAD.';

  @override
  String get filesGitXNoUpstream => '  ·  no upstream';

  @override
  String get filesGitXNotARepoSubtitle =>
      'Open this directory in a git project to see changes.';

  @override
  String get filesGitXNotARepoTitle => 'Not a git repository';

  @override
  String get filesGitXReconnectToSeeChanges =>
      'Reconnect the machine to see changes.';

  @override
  String get filesGitXRefreshTooltip => 'Refresh';

  @override
  String filesGitXSectionLabel(Object label, Object count) {
    return '$label · $count';
  }

  @override
  String get filesGitXSectionStaged => 'Staged';

  @override
  String get filesGitXSectionUnstaged => 'Unstaged';

  @override
  String get filesGitXSectionUntracked => 'Untracked';

  @override
  String filesGitXShowMoreLines(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Show $count more lines',
      one: 'Show $count more line',
    );
    return '$_temp0';
  }

  @override
  String get filesGitXShowWhitespaceTooltip => 'Show whitespace';

  @override
  String get filesGitXStatusNotLoaded =>
      'Git status not loaded on this device.';

  @override
  String get filesGitXWordWrapTooltip => 'Word Wrap';

  @override
  String get filesGitXWorkingTreeClean => 'Working tree clean';

  @override
  String get filesScreenTabChanges => 'Changes';

  @override
  String get filesScreenTabFiles => 'Files';

  @override
  String filesXErrDefault(Object code) {
    return 'Couldn’t list this directory ($code).';
  }

  @override
  String get filesXErrNoHandler =>
      'Update the daemon on this machine — older version doesn’t support file listing.';

  @override
  String get filesXErrNotADirectory => 'Project path is not a directory.';

  @override
  String get filesXErrOutsideProject => 'Path is outside the project root.';

  @override
  String get filesXErrPathNotFound =>
      'The project directory was not found on the machine.';

  @override
  String get filesXErrPermissionDenied =>
      'Permission denied reading this directory.';

  @override
  String get filesXErrTimeout => 'The machine took too long to respond.';

  @override
  String filesXMachineOffline(Object detail) {
    return 'Machine offline, $detail.';
  }

  @override
  String get filesXNoFiles => 'No files';

  @override
  String get filesXNotLoaded => 'Files not loaded on this device.';

  @override
  String get filesXOfflineDetailDefault => 'files could be outdated';

  @override
  String filesXProjectLabel(Object cwd) {
    return 'project: $cwd';
  }

  @override
  String get filesXReconnectToBrowse => 'Reconnect the machine to browse them.';

  @override
  String get filterAgentType => 'Agent Type';

  @override
  String get filterAgentTypeHeader => 'AGENT TYPE';

  @override
  String get filterAll => 'All';

  @override
  String get filterAllTime => 'All Time';

  @override
  String get filterClosed => 'Archived';

  @override
  String get filterCustomRange => 'Custom Range';

  @override
  String get filterDate => 'Date';

  @override
  String get filterDateRange => 'Date Range';

  @override
  String get filterDateRangeHeader => 'DATE RANGE';

  @override
  String get filterFilter => 'Filter';

  @override
  String get filterGroupBy => 'Group By';

  @override
  String get filterInProgress => 'In progress';

  @override
  String get filterInReview => 'In review';

  @override
  String get filterLast7Days => 'Last 7 Days';

  @override
  String get filterNotClosed => 'Active';

  @override
  String get filterProject => 'Project';

  @override
  String get filterStatus => 'Status';

  @override
  String get filterStatusHeader => 'STATUS';

  @override
  String get filterTime => 'Time';

  @override
  String get filterType => 'Type';

  @override
  String get giftDialogFreeCredits => 'Yay! You got 5 free credits!';

  @override
  String get helpFeedbackBlog => 'Blog';

  @override
  String get helpFeedbackChangelog => 'Changelog';

  @override
  String get helpFeedbackContactUs => 'Contact Us';

  @override
  String get helpFeedbackDocumentation => 'Documentation';

  @override
  String get helpFeedbackFeatureRequest => 'Feature Request & Bug Reports';

  @override
  String get helpFeedbackFeedback => 'Feedback';

  @override
  String get helpFeedbackTitle => 'Help & Feedback';

  @override
  String get homeCloseFailed => 'Failed to archive session. Please try again.';

  @override
  String get homeDeleteFailed => 'Failed to delete session. Please try again.';

  @override
  String get homeErrorConnecting =>
      'Connecting to the server. If this persists, sign in again from Account Page.';

  @override
  String get homeErrorLoadSessionsFailed =>
      'Failed to load sessions. Please try again.';

  @override
  String get homeErrorOffline =>
      'No internet connection. Please check your connection.';

  @override
  String get homeErrorOfflineCached =>
      'No internet connection. Showing cached data.';

  @override
  String get homeErrorServiceUnavailable =>
      'Unable to reach the service right now.';

  @override
  String get homeErrorServiceUnavailableRetry =>
      'Unable to reach the service right now. Please try again shortly.';

  @override
  String get homeErrorSessionExpired =>
      'Your session has expired. Please sign in again to continue.';

  @override
  String get homeGroupNoProject => 'No Project';

  @override
  String get homeGroupPinned => 'Pinned';

  @override
  String get homePinFailed => 'Couldn\'t pin session';

  @override
  String get homeRenameFailed => 'Failed to rename session. Please try again.';

  @override
  String get homeSessionClosed => 'Session archived';

  @override
  String get homeSessionDeleted => 'Session deleted successfully';

  @override
  String get homeSessionRenamed => 'Session renamed successfully';

  @override
  String get homeUnpinFailed => 'Couldn\'t unpin session';

  @override
  String impactHeadline(Object phrase) {
    return '$phrase with AI coding agents anywhere you go';
  }

  @override
  String get impactWithRatingHeadline =>
      'Build faster with AI coding agents anywhere you go';

  @override
  String get impactWithRatingNameMarcus => 'Marcus';

  @override
  String get impactWithRatingNameSarah => 'Sarah';

  @override
  String get impactWithRatingNameTom => 'Tom';

  @override
  String get impactWithRatingTestimonialMarcus =>
      'Vicoa changed how I work. I never miss opportunities to ship with all the coding agents in my phone.';

  @override
  String get impactWithRatingTestimonialSarah =>
      'Finally! Claude Code on mobile. I can code during my commute and fix bugs on the go.';

  @override
  String get impactWithRatingTestimonialTom =>
      'Perfect for developers on the move. Debug, refactor, and build new features from my phone. Amazing!';

  @override
  String get infoDialogAreYouSure => 'Are you sure?';

  @override
  String get introLandingPage1Item1 => 'Send commands from anywhere';

  @override
  String get introLandingPage1Item2 => 'Get instant AI responses';

  @override
  String get introLandingPage1Item3 => 'Sync across all devices';

  @override
  String get introLandingPage1Subtitle =>
      'Send commands to AI agent running on your computer, right from your phone.';

  @override
  String get introLandingPage1Title => 'Remote AI Coding\nfrom your Phone';

  @override
  String get introLandingPage2Item1 => 'Instant alerts when tasks done';

  @override
  String get introLandingPage2Item2 => 'One-tap approvals from your phone';

  @override
  String get introLandingPage2Item3 => 'Chat with your agents on the go';

  @override
  String get introLandingPage2Subtitle =>
      'Get instant alerts when your agent needs input and keep building without touching your laptop.';

  @override
  String get introLandingPage2Title => 'Your Agent Works.\nYou Stay Notified.';

  @override
  String get introLandingPage3Item1 =>
      'Works with Claude Code, Codex, and OpenCode';

  @override
  String get introLandingPage3Item2 => 'All your agent sessions in one place';

  @override
  String get introLandingPage3Item3 => 'Browse past conversations';

  @override
  String get introLandingPage3Subtitle =>
      'Monitor all your agents across projects, browse history, and more-all in one place.';

  @override
  String get introLandingPage3Title => 'One Interface for\nAll Your Agents';

  @override
  String get introLandingPage4Item1 => 'Download the desktop app';

  @override
  String get introLandingPage4Item2 => 'Sign in with the same account';

  @override
  String get introLandingPage4Item3 => 'Paired instantly! Start coding.';

  @override
  String get introLandingPage4Subtitle =>
      'A few clicks and you\'re ready to manage desktop projects right from your phone.';

  @override
  String get introLandingPage4Title => 'Connect in Seconds';

  @override
  String get landingHeadline => 'Remote AI coding\nfrom your phone';

  @override
  String get landingSubtitle => 'Run dozens of coding agents anywhere';

  @override
  String get landingSupports => 'Supports';

  @override
  String get languageAutomatic => 'Automatic';

  @override
  String get languageChinese => '中文';

  @override
  String get languageEnglish => 'English';

  @override
  String get languageFollowSystem => 'Follow system';

  @override
  String get machineActionsRemoveContent =>
      'Are you sure you want to remove this machine? You won\'t be able to start new sessions from it until you run the Vicoa CLI again.';

  @override
  String get machineActionsRemoveTitle => 'Remove Machine';

  @override
  String get machineActionsRemoving => 'Removing machine...';

  @override
  String get machineActionsRenamePlaceholder => 'Enter machine name...';

  @override
  String get machineActionsRenameTitle => 'Rename Machine';

  @override
  String get machineActionsRenaming => 'Renaming machine...';

  @override
  String get machineDetailAgentNotFound => 'Not found';

  @override
  String get machineDetailAgents => 'Agents';

  @override
  String get machineDetailCautionZone => 'Caution Zone';

  @override
  String get machineDetailCouldNotLoad => 'Could not load machine';

  @override
  String get machineDetailHomeDirectory => 'Home directory';

  @override
  String get machineDetailHostname => 'Hostname';

  @override
  String get machineDetailInstalled => 'Installed';

  @override
  String get machineDetailLastHeartbeat => 'Last heartbeat';

  @override
  String get machineDetailMachine => 'Machine';

  @override
  String get machineDetailNotFound => 'Machine not found';

  @override
  String get machineDetailOffline => 'Offline';

  @override
  String get machineDetailOnline => 'Online';

  @override
  String get machineDetailPlatform => 'Platform';

  @override
  String get machineDetailRemoveDescription =>
      'Remove this machine from your account. Session history will be preserved, but you will not be able to start new sessions on this machine.';

  @override
  String get machineDetailRemoveMachine => 'Remove machine';

  @override
  String get machineDetailRunPrefix => 'Run ';

  @override
  String get machineDetailRunSuffix => ' to bring it online';

  @override
  String get machineDetailStatus => 'Status';

  @override
  String get machineDetailSystem => 'System';

  @override
  String get machineDetailUnknown => 'Unknown';

  @override
  String get machineDetailVicoaCli => 'Vicoa CLI';

  @override
  String get machinesCouldNotLoad => 'Could not load machines';

  @override
  String get machinesMachineRemoved => 'Machine removed';

  @override
  String get machinesNoMachinesSubtitle =>
      'Run the Vicoa CLI on a computer to connect it, then start remote sessions from anywhere.';

  @override
  String get machinesNoMachinesYet => 'No machines yet';

  @override
  String get machinesPullToRefresh => 'Pull to refresh to try again.';

  @override
  String get machinesTitle => 'Machines';

  @override
  String markdownXMoreLines(Object count) {
    return '$count more lines';
  }

  @override
  String messageSelectionSheetCount(Object selected, Object total) {
    return '$selected of $total selected';
  }

  @override
  String get messageSelectionSheetDeselectAll => 'Deselect All';

  @override
  String get messageSelectionSheetSelectAll => 'Select All';

  @override
  String get messageSelectionSheetTitle => 'Select Messages';

  @override
  String get messageSelectionSheetYou => 'You';

  @override
  String get newSessionAddToChat => 'Add to chat';

  @override
  String get newSessionAgent => 'Agent';

  @override
  String newSessionAgentDidNotStart(Object label) {
    return '$label didn\'t start on this machine.\n\nMake sure it\'s installed there and your Vicoa daemon is up to date, then try again.';
  }

  @override
  String get newSessionCurrentBranch => 'Current branch';

  @override
  String get newSessionLoadingMachines => 'Loading machines...';

  @override
  String get newSessionMachine => 'Machine';

  @override
  String get newSessionNewSession => 'New Session';

  @override
  String get newSessionNewWorktree => 'New worktree';

  @override
  String get newSessionOffline => '(offline)';

  @override
  String get newSessionRunPrefix => 'Run ';

  @override
  String get newSessionSelectMachine => 'Select a machine';

  @override
  String get newSessionStartedNoStatus =>
      'Session started but could not determine status.';

  @override
  String get newSessionTheAgent => 'The agent';

  @override
  String get newSessionToBringOnline => ' to bring your machine online.';

  @override
  String get newSessionUnableToStart => 'Unable to Start Session';

  @override
  String get newSessionUnableToStartBody =>
      'This could be due to:\n\n• The machine is not responding\n• Network connection issues\n• The directory path is invalid\n\nPlease check machine status and try again.';

  @override
  String get newSessionWorkingDirectory => 'Working Directory';

  @override
  String get newSessionWorktree => 'Worktree';

  @override
  String get newsAndConnector => ' and ';

  @override
  String get newsBadNewsPrefix => 'The bad news is that\n';

  @override
  String get newsCodeFromPhone => 'code from your phone.';

  @override
  String get newsCodingNext12Months => '\ncoding in the next 12 months.';

  @override
  String get newsGetNotified => 'get notified';

  @override
  String get newsGreatNewsPrefix => 'The great news is that \n';

  @override
  String get newsJustWaiting => 'just waiting for the results';

  @override
  String get newsMinutesUnit => ' minutes ';

  @override
  String get newsTransitHeadline =>
      'Some not-so-good news  \nand some great news';

  @override
  String get newsVicoaFreesYouUp => 'Vicoa frees you up, you can ';

  @override
  String newsWastedMinutes(Object minutes) {
    return '$minutes+ minutes ';
  }

  @override
  String get newsYouWillSpend => 'You will spend ';

  @override
  String get newsYouWillWaste => 'You will waste ';

  @override
  String get noCreditSheetGetMoreFreeMessages => 'Get More Free Messages';

  @override
  String get noCreditSheetGetMoreOrUnlock =>
      'Get more free messages or unlock unlimited access with Vicoa Pro.';

  @override
  String get noCreditSheetInsufficientCredits => 'Insufficient Credits';

  @override
  String get noCreditSheetUpgradeToPro => 'Upgrade to Vicoa Pro';

  @override
  String get noCreditSheetUsedAllMessages => 'You\'ve used all free messages.';

  @override
  String get notificationAllSet => 'You are all set!';

  @override
  String get notificationDontMissOut =>
      'Don\'t miss out notifications when your coding agent needs your input.\n';

  @override
  String get notificationEnableButton => 'Enable Notification';

  @override
  String get notificationInOnboardBody =>
      'Don\'t miss out notifications when your coding agent needs your input.\n';

  @override
  String get notificationInOnboardEnable => 'Enable Notifications';

  @override
  String get notificationInOnboardMaybeLater => 'Maybe later';

  @override
  String get notificationInOnboardTitle => 'Turn on Notifications?';

  @override
  String get notificationTitle => 'Notifications';

  @override
  String get notificationTurnOnPrompt => 'Turn on Notification?';

  @override
  String get onboardGetNotifiedInstantly => 'Get notified instantly.';

  @override
  String get onboardGetStarted => 'Get Started';

  @override
  String get onboardNoMoreIdleWaiting => 'No more idle waiting.';

  @override
  String get onboardPickUpWhereLeftOff => 'Pick up where you left off.';

  @override
  String get onboardSlide1Body =>
      'Start a task, let Claude Code, Codex, or OpenCode keep working while you focus elsewhere.';

  @override
  String get onboardSlide2Body =>
      'Take AI coding agents anywhere, continue your coding on your phone.';

  @override
  String get onboardSlide3Body =>
      'Get a ping when AI coding agents needs input, continue coding with a tap.';

  @override
  String get personalizingConfiguringBest =>
      'Configuring the best set up for you';

  @override
  String get personalizingHeadline => 'Your AI Agents\nare almost ready';

  @override
  String get personalizingSettingUp => 'Setting Up';

  @override
  String get personalizingSocialProof =>
      'People who use Vicoa get more done\nwith coding agents.';

  @override
  String get proBenefitsPrioritySupportDesc =>
      'Get faster response times and priority support when you need help.';

  @override
  String get proBenefitsPrioritySupportTitle => 'Priority Support';

  @override
  String get proBenefitsSubtitle =>
      'You\'re enjoying all the premium features:';

  @override
  String get proBenefitsSyncDesc =>
      'Seamlessly sync your conversations and data across all your devices.';

  @override
  String get proBenefitsSyncTitle => 'Unlimited Cross-Device Sync';

  @override
  String get proBenefitsTitle => 'Vicoa Pro Benefits';

  @override
  String get proBenefitsUnlimitedMessagesDesc =>
      'Send unlimited messages to AI coding agents anywhere without any limits.';

  @override
  String get proBenefitsUnlimitedMessagesTitle => 'Unlimited Messages';

  @override
  String get proBenefitsVoiceInputDesc =>
      'Talk to your AI coding agents hands-free.';

  @override
  String get proBenefitsVoiceInputTitle => 'Voice Input';

  @override
  String get profileAccount => 'Account';

  @override
  String get profileAppearance => 'Appearance';

  @override
  String get profileFreeMessages => 'Free Messages';

  @override
  String get profileHelpFeedback => 'Help & Feedback';

  @override
  String get profileInviteFriends => 'Invite Friends & Get Rewards';

  @override
  String get profileJoinDiscord => 'Join Discord';

  @override
  String get profileJoinPro => 'Join Vicoa Pro';

  @override
  String get profileMachines => 'Machines';

  @override
  String get profileNotifications => 'Notifications';

  @override
  String get profileProMember => 'Vicoa Pro Member';

  @override
  String get profileProSubtitle => 'Unlimited Agents and Messages';

  @override
  String get profileReportIssue => 'Report an Issue';

  @override
  String get profileSubscription => 'Subscription';

  @override
  String get profileTitle => 'Profile';

  @override
  String get profileTutorials => 'Tutorials';

  @override
  String get profileVoiceAssistance => 'Voice Assistance';

  @override
  String get ratingDevelopersLike => '+100 developers like Vicoa';

  @override
  String get ratingLetsGetStarted => 'Let\'s get started';

  @override
  String get ratingMadeForYou => 'Vicoa was made for \npeople like you';

  @override
  String get ratingTestimonialMarcus =>
      'Vicoa changed how I work. Having OpenCode anywhere means I never miss opportunities to ship.';

  @override
  String get ratingTestimonialSarah =>
      'Finally! Claude Code on mobile. I can code during my commute and fix bugs on the go.';

  @override
  String get ratingTestimonialTom =>
      'Perfect for developers on the move. Debug, refactor, and build new features from my phone - amazing!';

  @override
  String get ratingTitle => 'Give us a rating';

  @override
  String get realtimeStatusBannerReconnecting => 'Reconnecting…';

  @override
  String get referFriendsAdditionalRewards => 'Additional Rewards';

  @override
  String get referFriendsCodeUnavailableBody =>
      'We\'re unable to generate your referral code at the moment. Please try again later or reach out for help.';

  @override
  String get referFriendsCodeUnavailableTitle => 'Referral Code Unavailable';

  @override
  String get referFriendsComeBackToClaim =>
      'Come back to claim free messages after your friend uses your code.';

  @override
  String get referFriendsContinueToUse => 'Continue to Use';

  @override
  String get referFriendsCopiedToClipboard => 'Copied to clipboard';

  @override
  String get referFriendsEmailUs => 'Email us';

  @override
  String referFriendsGotRewardMessages(Object count) {
    return 'Yay! You got $count free messages for referring friends!';
  }

  @override
  String get referFriendsGrabYourCode => 'Grab Your Referral Code';

  @override
  String referFriendsInvitedCount(Object count) {
    return '$count invited';
  }

  @override
  String get referFriendsOnlyRegisteredUsers =>
      'Only registered users can invite friends.';

  @override
  String referFriendsShareMessage(Object code) {
    return 'Hey, have you heard of Vicoa? With this app, I can run Claude Code, Codex, or OpenCode anywhere on my phone. You will get 50 free messages using my referral code: $code. Download the app from https://apps.apple.com/app/id6751626168';
  }

  @override
  String get referFriendsShareSubject =>
      'Vicoa: Code with AI Anytime, Anywhere';

  @override
  String get referFriendsShareYourCode => 'Share your referral code';

  @override
  String get referFriendsSignUpNow => 'Sign Up Now';

  @override
  String get referFriendsSignupReward =>
      '✅ 50 free messages when they sign up with your referral code.';

  @override
  String get referFriendsTheyGet => 'They get';

  @override
  String referFriendsTierBenefit(Object count, Object reward) {
    return '$count friends → $reward free messages';
  }

  @override
  String get referFriendsTitle => 'Invite Friends & Get Rewards';

  @override
  String get referFriendsYouGet => 'You get';

  @override
  String get rpcErrorComputerOffline =>
      'Your computer isn\'t connected right now. Make sure Vicoa is running on it, then try again.';

  @override
  String get rpcErrorTimeout =>
      'Your computer took too long to respond. Check that Vicoa is running on it, then try again.';

  @override
  String get referralCodeHint => 'Referral Code (Optional)';

  @override
  String get referralCodeThisIsOptional => 'This is optional';

  @override
  String get referralCodeTitle => 'Do you have a \nReferral Code?';

  @override
  String relativeTimeHours(int count) {
    return '${count}h';
  }

  @override
  String relativeTimeMinutes(int count) {
    return '${count}m';
  }

  @override
  String get relativeTimeNow => 'now';

  @override
  String relativeTimeSeconds(int count) {
    return '${count}s';
  }

  @override
  String get renameDialogEnterSessionName => 'Enter session name...';

  @override
  String get renameDialogRenameSession => 'Rename Session';

  @override
  String get reportIssueDialogFailure => 'Failed to send. Please try again.';

  @override
  String get reportIssueDialogHint => 'Describe the issue...';

  @override
  String get reportIssueDialogSending => 'Sending...';

  @override
  String get reportIssueDialogSubmit => 'Submit';

  @override
  String get reportIssueDialogSuccess => 'Report sent. Thanks!';

  @override
  String reviewDialogCharCount(Object current, Object max) {
    return '$current / $max';
  }

  @override
  String get reviewDialogCouldBeBetter => '🤔 Could be better';

  @override
  String get reviewDialogEnjoyingDescription =>
      'We\'d love to know if you are enjoying Vicoa. Your feedback helps us improve!';

  @override
  String get reviewDialogEnjoyingVicoa => 'Enjoying Vicoa?';

  @override
  String get reviewDialogIssueHint => 'The issue is…';

  @override
  String get reviewDialogLoveIt => '😍 Love it!';

  @override
  String get reviewDialogNeedsWorkDescription =>
      'Something not quite right? Tell us, so we can make it work for you.';

  @override
  String get reviewDialogRateOnAppStore => 'Rate on App Store';

  @override
  String get reviewDialogReviewDescription =>
      'Your review helps spread the word and motivate us to make Vicoa even better!';

  @override
  String get reviewDialogReviewVicoa => 'Review Vicoa :)';

  @override
  String get reviewDialogSendFailed => 'Failed to send. Please try again.';

  @override
  String get reviewDialogSendFeedback => 'Send Feedback';

  @override
  String get reviewDialogSending => 'Sending…';

  @override
  String get reviewDialogThankYou => 'Thank you for your feedback!';

  @override
  String get reviewDialogWhatCouldBeBetter => 'What could be better?';

  @override
  String get sessionActionsArchive => 'Archive';

  @override
  String get chatOptionsResume => 'Resume';

  @override
  String get sessionResumeOffline =>
      'Your computer is offline. Bring it back online to resume.';

  @override
  String get sessionResumeFailed => 'Failed to resume session';

  @override
  String get sessionActionsCloseContent =>
      'Are you sure you want to archive this session?';

  @override
  String get sessionActionsCloseTitle => 'Archive Session';

  @override
  String get sessionActionsClosing => 'Archiving session...';

  @override
  String get sessionActionsDeleteContent =>
      'Are you sure you want to delete this session? This action cannot be undone.';

  @override
  String get sessionActionsDeleteTitle => 'Delete Session';

  @override
  String get sessionActionsDeleting => 'Deleting session...';

  @override
  String get sessionActionsRenamePlaceholder => 'Enter session name...';

  @override
  String get sessionActionsRenameTitle => 'Rename Session';

  @override
  String get sessionActionsRenaming => 'Renaming session...';

  @override
  String get sessionInfoAgent => 'Agent';

  @override
  String get sessionInfoAiAgent => 'AI Agent';

  @override
  String get sessionInfoCopyId => 'Copy ID';

  @override
  String get sessionInfoCreated => 'Created';

  @override
  String sessionInfoDateAtTime(Object date, Object time) {
    return '$date at $time';
  }

  @override
  String get sessionInfoEditTitle => 'Edit title';

  @override
  String get sessionInfoId => 'ID';

  @override
  String get sessionInfoIdCopied => 'Session ID copied to clipboard';

  @override
  String get sessionInfoLastUpdated => 'Last Updated';

  @override
  String get sessionInfoMachine => 'Machine';

  @override
  String get sessionInfoNameThisSession => 'Name this session';

  @override
  String get sessionInfoProject => 'Project';

  @override
  String get sessionInfoRenameFailed => 'Failed to rename session';

  @override
  String get sessionInfoRenamed => 'Session renamed';

  @override
  String get sessionInfoSessionInfo => 'Session Info';

  @override
  String get sessionInfoSessionName => 'Session Name';

  @override
  String get sessionInfoSourceApp => 'App';

  @override
  String get sessionInfoSourceTerminal => 'Terminal';

  @override
  String get sessionInfoStartedFrom => 'Started From';

  @override
  String get sessionInfoViewMachine => 'View machine';

  @override
  String get sessionInfoWorktree => 'Worktree';

  @override
  String get sessionListClosed => 'Session archived';

  @override
  String get sessionListDeleted => 'Session deleted successfully';

  @override
  String get setupReminderNotificationBody =>
      'Download the Vicoa desktop app on your computer and sign in — start using Claude Code, Codex, and OpenCode on the go.';

  @override
  String get setupReminderNotificationTitle =>
      'Bring coding agents to your phone 🚀';

  @override
  String get shareOptionsSheetCopiedToClipboard =>
      'Content copied to clipboard';

  @override
  String get shareOptionsSheetCopyToClipboard => 'Copy to clipboard';

  @override
  String get shareOptionsSheetShareAs => 'Share as';

  @override
  String get shareOptionsSheetShareAsFile => 'Share as a file';

  @override
  String get shareOptionsSheetShareAsText => 'Share as text';

  @override
  String get signInDialogBody => 'Please sign in to use the feature.';

  @override
  String get signInDialogLater => 'I\'ll DO IT LATER';

  @override
  String get signInDialogTitle => 'Sign In To Continue';

  @override
  String get signUpAlreadyHaveAccount => 'Already have an account? ';

  @override
  String get signUpCreateAccount => 'Create Account';

  @override
  String get signUpDontHaveAccount => 'Don\'t have an account? ';

  @override
  String get signUpEmailLabel => 'Email address';

  @override
  String get signUpHaveReferralCode => 'I have a referral code';

  @override
  String get signUpPasswordLabel => 'Password';

  @override
  String get signUpPasswordsMismatch => 'Passwords don\'t match!';

  @override
  String get signUpReferralCodeLabel => 'Referral code (optional)';

  @override
  String get signUpReferralCreditsNotGrantedBody =>
      'We couldn\'t grant your referral credits. Please contact us for support if you have any questions.';

  @override
  String get signUpReferralCreditsNotGrantedTitle =>
      'Referral Credits Not Granted';

  @override
  String get signUpReferralInvalidBody =>
      'Your referral code doesn\'t seem to be valid. Please check it and try again later or remove it. If you have any questions, feel free to contact me at hi@vicoa.ai.';

  @override
  String get signUpReferralInvalidTitle => 'Failed to Apply Referral Code';

  @override
  String get signUpRemoveReferralCode => 'Remove referral code';

  @override
  String get signUpSignInLink => 'Sign in';

  @override
  String get signUpSignUpLink => 'Sign up';

  @override
  String signUpSubtitleSignIn(Object phrase) {
    return 'Sign in to $phrase with AI coding agents anywhere you go';
  }

  @override
  String get signUpSubtitleSignUp =>
      'Sign up to run a team of coding agents\nanywhere you go';

  @override
  String get startSessionAgent => 'Agent';

  @override
  String startSessionAgentComingSoon(Object name) {
    return '$name (Coming Soon)';
  }

  @override
  String get startSessionLoadingMachines => 'Loading machines...';

  @override
  String get startSessionMachine => 'Machine';

  @override
  String get startSessionNewSession => 'New Session';

  @override
  String get startSessionOffline => '(offline)';

  @override
  String get startSessionOrSeparator => ' or ';

  @override
  String get startSessionRecent => 'Recent';

  @override
  String get startSessionRunPrefix => 'Run ';

  @override
  String get startSessionSelectMachine => 'Select a machine';

  @override
  String get startSessionShowMore => 'Show more';

  @override
  String get startSessionStartSession => 'Start Session';

  @override
  String get startSessionStartedNoStatus =>
      'Session started but could not determine status. Please try again.';

  @override
  String get startSessionToBringOnline => ' to bring your machine online.';

  @override
  String get startSessionUnableToStart => 'Unable to Start Session';

  @override
  String get startSessionUnableToStartBody =>
      'This could be due to:\n\n• The machine is not responding\n• Network connection issues\n• The directory path is invalid\n\nPlease check machine status and try again.';

  @override
  String get startSessionWorkingDirectory => 'Working Directory';

  @override
  String get surveyDefaultQuestion => 'What is your goal?';

  @override
  String get surveyOpt1to2h => '1–2 hours';

  @override
  String get surveyOpt2to4h => '2–4 hours';

  @override
  String get surveyOpt4to8h => '4–8 hours';

  @override
  String get surveyOptCodePhone => '📱 I want to code from my phone';

  @override
  String get surveyOptDataScientist => 'Data Scientist / Analyst';

  @override
  String get surveyOptResearcher => 'Researcher';

  @override
  String get surveyOptDesign => 'Design';

  @override
  String get surveyOptDeveloper => 'Developer';

  @override
  String get surveyOptFinance => 'Finance';

  @override
  String get surveyOptFounder => 'Founder';

  @override
  String get surveyOptFreelancer => 'Freelancer';

  @override
  String get surveyOptGt8h => '>8 hours';

  @override
  String get surveyOptLoseTrack => '🔀 I lose track of my agents\' work';

  @override
  String get surveyOptLt1h => '<1 hour';

  @override
  String get surveyOptMarketing => 'Marketing';

  @override
  String get surveyOptNoComputer => 'I don\'t use computer';

  @override
  String get surveyOptNotAtComputer => '📍 I can\'t always be at my computer';

  @override
  String get surveyOptOthers => 'Others';

  @override
  String get surveyOptProduct => 'Product';

  @override
  String get surveyOptStuckDesk => '🖥️ I\'m stuck at my desk coding with AI';

  @override
  String get surveyOptStudent => 'Student';

  @override
  String get surveyOptTooManySessions => '🤯 I juggle too many coding sessions';

  @override
  String get surveyOptWaitAi => '⏳ I often wait for AI to finish tasks';

  @override
  String get surveyQAiTools => 'Which AI coding tools\ndo you use?';

  @override
  String get surveyQDailyTime => 'How long do you\ncode with AI daily?';

  @override
  String get surveyQDescribeYou => 'Which best describes you?';

  @override
  String get surveyQOs => 'Which operating system is\non your computer?';

  @override
  String get surveyQResonate => 'Which of these do you\nresonate with?';

  @override
  String get surveySelectAllThatApply => 'Select all that apply';

  @override
  String get surveyTypeYourAnswer => 'Type your answer...';

  @override
  String get surveyWithImpactMotivationAlerts =>
      'Perfect, Vicoa alerts you when AI finishes tasks.';

  @override
  String get surveyWithImpactMotivationCodeFromPhone =>
      'Perfect, Vicoa is great for coding from your phone.';

  @override
  String get surveyWithImpactMotivationDefault =>
      'Vicoa helps you code with AI on your phone.';

  @override
  String get surveyWithImpactMotivationFreeFromDesk =>
      'Perfect, Vicoa frees you from your desk to code on the go.';

  @override
  String get surveyWithImpactMotivationMultipleAgents =>
      'Perfect, Vicoa is great for managing multiple agents.';

  @override
  String get surveyWithImpactMotivationOnTrack =>
      'Perfect, Vicoa keeps you on track of your agents.';

  @override
  String get surveyWithImpactMotivationSendCommands =>
      'Perfect, Vicoa notifies you and allows you to send commands from your phone.';

  @override
  String get tutorialTitle => 'Tutorials';

  @override
  String usageCreditsCanStillSend(Object count) {
    return 'You can still send $count messages for free.';
  }

  @override
  String get usageCreditsFreeMessages => 'Free Messages';

  @override
  String get usageCreditsGetMoreFreeMessages => 'Get more free messages';

  @override
  String get usageCreditsGiftComingSoon =>
      'Coming soon: gift your free messages to friends!';

  @override
  String get usageCreditsInviteFriends => 'Invite Friends';

  @override
  String get usageCreditsLearnMore => 'Learn More';

  @override
  String get usageCreditsRateUs5Stars => 'Rate Us 5 Stars';

  @override
  String get usageCreditsStartFreeTrialNow => 'Start Free Trial Now 👋';

  @override
  String get usageCreditsUnlimitedMessagesAgents =>
      'Unlimited Messages & Agents';

  @override
  String get usageCreditsYourMessages => 'Your Messages';

  @override
  String get versionUpdateDialogBody =>
      'A new version of Vicoa is available. Please update your app to use all of our amazing features.';

  @override
  String get versionUpdateDialogLater => 'I\'ll DO IT LATER';

  @override
  String get versionUpdateDialogTitle => 'New version available';

  @override
  String get versionUpdateDialogUpdateNow => 'UPDATE NOW';

  @override
  String get videoPlayerXError => 'Error playing video';

  @override
  String get videoPlayerXLoading => 'Loading';

  @override
  String get voiceAssistanceDescription =>
      'Choose the language for voice dictation in chat.';

  @override
  String get voiceAssistanceTitle => 'Voice Assistance';

  @override
  String get voiceAssistanceTranscriptionLanguage => 'Transcription Language';

  @override
  String get voiceLanguageSearchHint => 'Search language';

  @override
  String get voiceLanguageTitle => 'Voice Language';

  @override
  String get webPreviewBeta => 'beta';

  @override
  String get webPreviewEnterUrl => 'Enter URL';

  @override
  String webPreviewHttpStatus(Object statusCode) {
    return 'The server returned HTTP $statusCode.';
  }

  @override
  String get webPreviewSiteUnreachable => 'This site can\'t be reached';

  @override
  String get webPreviewTitle => 'Live Preview';

  @override
  String webPreviewUrlUnreachableDetails(Object details) {
    return 'This URL could not be reached. $details';
  }

  @override
  String get webPreviewUrlUnreachableHint =>
      'This URL could not be reached. Check that the preview server is running and the tunnel URL is still valid.';

  @override
  String get webPreviewWebUnavailable =>
      'Web preview is available on iOS/Android app builds.';

  @override
  String get welcomeAnswerQuickQuestions =>
      'Answer a few quick questions to personalize your experience';

  @override
  String welcomeDemoCancelSubscription(Object url) {
    return 'Heads up: Vicoa needs a computer to run, so if you\'re on a trial you may want to **cancel it to avoid charges**.\n\n[How to cancel your subscription →]($url)';
  }

  @override
  String get welcomeDemoCardTapToSee => 'Tap to see how Vicoa works';

  @override
  String get welcomeDemoCardWelcome => 'Welcome to Vicoa';

  @override
  String get welcomeDemoCta => 'Ready to try it for real? Pick what fits you:';

  @override
  String get welcomeDemoInstanceName => 'Welcome to Vicoa 👋';

  @override
  String get welcomeDemoLatestMessage =>
      'Ready when you are — pick how you want to start.';

  @override
  String get welcomeDemoMsg1 =>
      '👋 **Welcome to Vicoa!**\n\nVicoa lets you orchestrate dozens of coding agents in parallel, anywhere. \n\nThis sample chat shows what a coding session looks like after you start using Vicoa.👇';

  @override
  String get welcomeDemoMsg2 => 'How do I use Vicoa?';

  @override
  String get welcomeDemoMsg3 =>
      '📱 **Start from phone**: tap **+** button, start a new coding session.\n\n🖥️ **Start from computer**: start coding at your desk, continue on the phone.\n';

  @override
  String get welcomeDemoMsg4 => 'What can I do?';

  @override
  String get welcomeDemoMsg5 =>
      '- 💬 Chat with your agent\n- 🔔 Get notified when tasks done\n- ✅ Approve actions\n- 👀 See code changes\n- And many more...';

  @override
  String get welcomeDemoMsg8 => 'Which agents work with Vicoa?';

  @override
  String get welcomeDemoMsg9 =>
      'Whichever you already use:\n| Agent | Models |\n| --- | --- |\n| Claude Code | e.g., Opus 4.8, Opus 4.7, Sonnet 4.6 |\n| Codex | e.g., GPT-5.5, GPT-5.4 |\n| OpenCode | e.g., Z.AI, Minimax, DeepSeek |\n| Gemini | e.g., Gemini 3 Pro, Gemini 2.5 Flash |\n| Cursor | e.g., Composer, Claude, GPT |\n| Copilot | e.g., Claude, GPT, Gemini |\n| Kimi | e.g., Kimi K2.5, K2.6, K2.7 Code |\n| Hermes | 50+ models |\n\n> You bring your own agent, Vicoa just connects it.\n\nCoding agents make changes, Vicoa show you in real-time: \n\n';

  @override
  String get welcomeDemoNoComputerSubtitle => 'Tell us what you want instead';

  @override
  String get welcomeDemoNoComputerTitle => 'I don\'t have a computer with me';

  @override
  String get welcomeDemoSetupCliSubtitle => 'Email me a get-started link';

  @override
  String get welcomeDemoSetupCliTitle => 'I\'ll set up Vicoa on my computer';

  @override
  String welcomeDemoSetupEmailSent(Object target) {
    return '📧 We\'ve sent a get-started link to $target.\n\n';
  }

  @override
  String get welcomeDemoSetupEmailTargetFallback => 'your inbox';

  @override
  String get welcomeDemoSetupInstructions =>
      'Here\'s how to get set up on your computer:\n\n1. Download the desktop app: **https://vicoa.ai/download**\n2. Open it and sign in with this account. Your computer and phone are connected automatically\n\nPrefer the command line? Follow the [setup guide](https://vicoa.ai/docs/getting-started).\n\nHappy building!\n';

  @override
  String get welcomeDemoSetupQuestion => 'How do I start?';

  @override
  String get welcomeDemoWaitlistHeader => 'Quick question';

  @override
  String get welcomeDemoWaitlistIntro =>
      'No problem. Vicoa needs a computer today, but we\'re working on more. Tell us what you\'re after and we\'ll keep you posted:';

  @override
  String get welcomeDemoWaitlistOptDev =>
      'I\'m a developer. My computer is not with me right now';

  @override
  String get welcomeDemoWaitlistOptGithub =>
      'I\'m a developer. I want to connect GitHub and work fully from my phone';

  @override
  String get welcomeDemoWaitlistOptNotDev =>
      'I\'m not a developer. I just want to build apps on my phone';

  @override
  String get welcomeDemoWaitlistPrompt => 'Join the waitlist';

  @override
  String get welcomeDemoWaitlistQuestion =>
      'What do you want to do with Vicoa?';

  @override
  String get welcomeDemoWaitlistThanks =>
      '🙌 Thank you! You\'re on the list. We\'ll reach out as soon as there\'s a great way for you to get started.';

  @override
  String get welcomeGladToHaveYou => 'Glad to have you with us 👋';

  @override
  String get welcomeSkipForNow => 'Skip for now';

  @override
  String get welcomeStartYourJourney =>
      'Let\'s start your journey to \nvibe code anywhere.';

  @override
  String get worktreeActionsActiveSession =>
      'A session is still running in this worktree.';

  @override
  String get worktreeActionsCleanupContent =>
      'This session ran in a vicoa worktree with no remaining changes. Delete the worktree, or keep the files?';

  @override
  String get worktreeActionsCleanupTitle => 'Delete worktree?';

  @override
  String get worktreeActionsDeleted => 'Worktree deleted.';

  @override
  String worktreeActionsRemoveContent(Object branch) {
    return 'Remove the worktree \"$branch\"? The branch is kept, so commits on it stay safe.';
  }

  @override
  String worktreeActionsRemoveDirtyContent(Object branch) {
    return 'The worktree \"$branch\" has uncommitted changes. Remove it anyway? The branch is kept, so any commits on it stay safe.';
  }

  @override
  String get worktreeActionsRemoveFailed => 'Couldn\'t remove worktree.';

  @override
  String worktreeActionsRemoveFailedCode(Object code) {
    return 'Couldn\'t remove worktree: $code';
  }

  @override
  String get worktreeActionsRemoveTitle => 'Remove worktree';

  @override
  String get worktreeActionsRemoved => 'Worktree removed.';

  @override
  String get worktreeActionsThisWorktree => 'this worktree';

  @override
  String get worktreeDetailBranch => 'Branch';

  @override
  String get worktreeDetailCopyPath => 'Copy path';

  @override
  String get worktreeDetailInUseDescription =>
      'A session is still running in this worktree. End it before removing.';

  @override
  String get worktreeDetailNotManagedNote =>
      'This worktree wasn\'t created by Vicoa, so it can\'t be managed from the app.';

  @override
  String get worktreeDetailOrigin => 'Origin';

  @override
  String get worktreeDetailOriginExternal => 'External';

  @override
  String get worktreeDetailOriginVicoa => 'Vicoa';

  @override
  String get worktreeDetailPath => 'Path';

  @override
  String get worktreeDetailPathCopied => 'Path copied to clipboard';

  @override
  String get worktreeDetailRemoveDescription =>
      'Removes the worktree\'s checkout. The branch is kept, so commits stay safe.';

  @override
  String get worktreeDetailRemoveWorktree => 'Remove worktree';

  @override
  String get worktreeDetailStatus => 'Status';

  @override
  String get worktreeDetailStatusIdle => 'Idle';

  @override
  String get worktreeDetailStatusInUse => 'In use, a session is running';

  @override
  String get worktreeDetailWorktree => 'Worktree';

  @override
  String get worktreePickerCurrentBranch => 'Current branch';

  @override
  String get worktreePickerCurrentBranchSubtitle =>
      'No worktree · run in the directory';

  @override
  String get worktreePickerDetached => '(detached)';

  @override
  String get worktreePickerExistingWorktrees => 'Existing worktrees';

  @override
  String worktreePickerExternalPath(Object path) {
    return '$path · external';
  }

  @override
  String get worktreePickerLoadFailed => 'Couldn\'t load worktrees';

  @override
  String get worktreePickerNewWorktree => 'New worktree';

  @override
  String get worktreePickerNewWorktreeSubtitle =>
      'Fork a fresh branch off HEAD';

  @override
  String get worktreePickerNotARepo =>
      'This directory isn\'t a git repository — only the current branch is available.';

  @override
  String get worktreePickerWorktree => 'Worktree';

  @override
  String get worktreesCouldNotLoad => 'Couldn\'t load worktrees';

  @override
  String get worktreesDetached => '(detached)';

  @override
  String get worktreesNoWorktreesSubtitle =>
      'Start a session in a new worktree to create one. It\'ll show up here for you to manage.';

  @override
  String get worktreesNoWorktreesYet => 'No worktrees yet';

  @override
  String get worktreesNotAGitRepo => 'Not a git repository';

  @override
  String get worktreesNotAGitRepoSubtitle =>
      'This directory isn\'t a git repository.';

  @override
  String get worktreesPullToRefresh => 'Pull to refresh to try again.';

  @override
  String get worktreesTitle => 'Worktrees';

  @override
  String get worktreesWorktreeRemoved => 'Worktree removed.';

  @override
  String get youtubeXInvalidUrl => 'Invalid YouTube URL';

  @override
  String get youtubeXNoVideoUrl => 'No video URL provided';

  @override
  String get sessionUsageTitle => 'Usage';

  @override
  String get sessionUsageContext => 'Context Window';

  @override
  String get sessionUsageTokensSuffix => 'tokens';

  @override
  String sessionUsageSessionCost(Object cost) {
    return 'Session cost $cost';
  }

  @override
  String get sessionUsageCredits => 'Credits';

  @override
  String sessionUsageCreditsLeft(Object amount) {
    return '$amount left';
  }

  @override
  String sessionUsageResetsAtTime(Object time) {
    return 'Resets $time';
  }

  @override
  String sessionUsageResetsOnDate(Object date, Object time) {
    return 'Resets $date at $time';
  }

  @override
  String get sessionUsageResettingNow => 'Resetting now';

  @override
  String get sessionUsageRefreshing => 'Refreshing…';

  @override
  String get automationsAgent => 'Agent';

  @override
  String get automationsAtMinute => 'At minute';

  @override
  String get automationsChooseFolder => 'Choose folder';

  @override
  String get automationsConnectMachineFirst =>
      'Connect a machine first to create an automation.';

  @override
  String get automationsCouldNotLoad => 'Couldn\'t load automations';

  @override
  String get automationsDate => 'Date';

  @override
  String get automationsDelete => 'Delete';

  @override
  String get automationsDeleteConfirmBody =>
      'This removes the automation and its run history. Sessions it already started are kept.';

  @override
  String get automationsDeleteConfirmTitle => 'Delete automation?';

  @override
  String get automationsDeleted => 'Automation deleted';

  @override
  String get automationsEditTitle => 'Edit Automation';

  @override
  String get automationsEmptySubtitle =>
      'Schedule an agent to run on automatically.';

  @override
  String get automationsEmptyTitle => 'No automations yet';

  @override
  String get automationsEvery => 'Every';

  @override
  String automationsEveryUnitDays(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'days',
      one: 'day',
    );
    return '$_temp0';
  }

  @override
  String automationsEveryUnitHours(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'hours',
      one: 'hour',
    );
    return '$_temp0';
  }

  @override
  String automationsEveryUnitMinutes(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'minutes',
      one: 'minute',
    );
    return '$_temp0';
  }

  @override
  String automationsEveryUnitMonths(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'months',
      one: 'month',
    );
    return '$_temp0';
  }

  @override
  String automationsEveryUnitWeeks(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'weeks',
      one: 'week',
    );
    return '$_temp0';
  }

  @override
  String get automationsFilterActive => 'Active';

  @override
  String get automationsFilterAll => 'All';

  @override
  String get automationsFilterPaused => 'Paused';

  @override
  String get automationsMachineOffline =>
      'Machine is offline — run could not start.';

  @override
  String get automationsNew => 'New Automation';

  @override
  String automationsNextRun(String when) {
    return 'Next · $when';
  }

  @override
  String get automationsNoRunsYet => 'No runs yet.';

  @override
  String get automationsPause => 'Pause';

  @override
  String get automationsProject => 'Project';

  @override
  String get automationsPromptPlaceholder =>
      'Describe what the agent should do';

  @override
  String get automationsPullToRefresh => 'Pull down to try again';

  @override
  String get automationsRepeat => 'Repeat';

  @override
  String get automationsRepeatCustom => 'Custom';

  @override
  String get automationsRepeatDaily => 'Daily';

  @override
  String get automationsRepeatHourly => 'Hourly';

  @override
  String get automationsRepeatMinutely => 'Minutely';

  @override
  String get automationsRepeatMonthly => 'Monthly';

  @override
  String get automationsRepeatOnce => 'Once';

  @override
  String get automationsRepeatWeekdays => 'Weekdays';

  @override
  String get automationsRepeatWeekly => 'Weekly';

  @override
  String get automationsRepeats => 'Repeats';

  @override
  String get automationsResume => 'Resume';

  @override
  String get automationsRunFailed => 'Run failed';

  @override
  String get automationsRunNow => 'Run now';

  @override
  String get automationsRunStarted => 'Run started';

  @override
  String get automationsRunStatusFailed => 'Failed';

  @override
  String get automationsRunStatusFired => 'Ran';

  @override
  String get automationsRunStatusMissedOffline => 'Missed — offline';

  @override
  String get automationsRunStatusSkipped => 'Skipped';

  @override
  String get automationsRunsOn => 'Runs on';

  @override
  String get automationsSaveFailed => 'Couldn\'t save automation';

  @override
  String automationsScheduleOnceAt(String when) {
    return 'Once · $when';
  }

  @override
  String get automationsSectionDetails => 'Details';

  @override
  String get automationsSectionFrequency => 'Frequency';

  @override
  String get automationsSectionRunHistory => 'Run history';

  @override
  String get automationsStatusPaused => 'Paused';

  @override
  String automationsSummaryDaily(String time) {
    return 'Daily at $time';
  }

  @override
  String automationsSummaryEveryDays(String n, String time) {
    return 'Every $n days at $time';
  }

  @override
  String automationsSummaryEveryHours(String n, String minute) {
    return 'Every $n hours at :$minute';
  }

  @override
  String automationsSummaryEveryMonths(String n, String days, String time) {
    return 'Every $n months on day $days at $time';
  }

  @override
  String automationsSummaryEveryWeeks(String n, String days, String time) {
    return 'Every $n weeks on $days at $time';
  }

  @override
  String automationsSummaryHourly(String minute) {
    return 'Hourly at :$minute';
  }

  @override
  String get automationsSummaryHourlyPlain => 'Hourly';

  @override
  String automationsSummaryEveryHoursPlain(String n) {
    return 'Every $n hours';
  }

  @override
  String automationsSummaryEveryMinutes(String n) {
    return 'Every $n minutes';
  }

  @override
  String get automationsSummaryRecurring => 'Recurring';

  @override
  String automationsSummaryWeekdays(String time) {
    return 'Weekdays at $time';
  }

  @override
  String automationsSummaryWeekly(String days, String time) {
    return 'Weekly on $days at $time';
  }

  @override
  String get automationsTime => 'Time';

  @override
  String get automationsTimeWindow => 'Time window';

  @override
  String get automationsWindowAllDay => 'All day';

  @override
  String get automationsWindowCustom => 'Custom';

  @override
  String get automationsWindowFrom => 'From';

  @override
  String get automationsWindowInvalid =>
      'The end time must be after the start time.';

  @override
  String get automationsWindowTo => 'To';

  @override
  String get automationsTitle => 'Automations';

  @override
  String get automationsTitlePlaceholder => 'Automation title';

  @override
  String get automationsTitleRequired => 'Title is required';

  @override
  String get tabAgents => 'Agents';

  @override
  String get tabAutomations => 'Automations';

  @override
  String get tabProfile => 'Profile';

  @override
  String get tabTasks => 'Tasks';

  @override
  String get searchHint => 'Search sessions, tasks, automations';

  @override
  String get searchRecent => 'Recent';

  @override
  String get searchSessions => 'Sessions';

  @override
  String get searchNoResults => 'No results found';

  @override
  String get searchPrompt => 'Type to search sessions, tasks, and automations';

  @override
  String get searchFailed =>
      'Search failed — check your connection and try again';

  @override
  String get searchTimeout => 'Search timed out — try a more specific query';

  @override
  String get searchSessionsOnly => 'Showing sessions only';

  @override
  String get gettingStartedTitle => 'Get started';

  @override
  String gettingStartedProgress(int done, int total) {
    return '$done of $total done';
  }

  @override
  String get gettingStartedConnectTitle => 'Connect a computer';

  @override
  String get gettingStartedConnectHint => 'Set up Vicoa on your desktop';

  @override
  String get gettingStartedSessionTitle => 'Start a session';

  @override
  String get gettingStartedSessionHint => 'Spin up a coding agent';

  @override
  String get gettingStartedMessageTitle => 'Send a message';

  @override
  String get gettingStartedMessageHint => 'Chat with your agent';

  @override
  String get gettingStartedCollapse => 'Collapse';

  @override
  String get gettingStartedDismiss => 'Dismiss';

  @override
  String get gettingStartedConnectSheetTitle => 'Set up Vicoa on your computer';

  @override
  String get gettingStartedConnectSheetBody =>
      'Vicoa runs your coding agents on your computer. Set it up on your desktop, then start, watch, and steer them from your phone.';

  @override
  String get gettingStartedEmailLinkCta => 'Email me the setup link';

  @override
  String get gettingStartedEmailSentCta => 'Setup link sent';

  @override
  String gettingStartedEmailSentToast(Object target) {
    return 'We\'ve sent a get-started link to $target.';
  }

  @override
  String get gettingStartedDownloadCta => 'Or open vicoa.ai/download';
}
