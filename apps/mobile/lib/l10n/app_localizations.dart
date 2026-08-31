import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_zh.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
      : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('zh')
  ];

  /// No description provided for @tasksAllProjects.
  ///
  /// In en, this message translates to:
  /// **'All projects'**
  String get tasksAllProjects;

  /// No description provided for @tasksCancel.
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get tasksCancel;

  /// No description provided for @tasksCouldNotLoad.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t load tasks'**
  String get tasksCouldNotLoad;

  /// No description provided for @tasksCreate.
  ///
  /// In en, this message translates to:
  /// **'Create'**
  String get tasksCreate;

  /// No description provided for @tasksDelete.
  ///
  /// In en, this message translates to:
  /// **'Delete'**
  String get tasksDelete;

  /// No description provided for @tasksDeleteConfirmBody.
  ///
  /// In en, this message translates to:
  /// **'This task will be permanently deleted. This can\'t be undone.'**
  String get tasksDeleteConfirmBody;

  /// No description provided for @tasksDeleteConfirmTitle.
  ///
  /// In en, this message translates to:
  /// **'Delete task?'**
  String get tasksDeleteConfirmTitle;

  /// No description provided for @tasksDescriptionFieldLabel.
  ///
  /// In en, this message translates to:
  /// **'DESCRIPTION'**
  String get tasksDescriptionFieldLabel;

  /// No description provided for @tasksDescriptionPlaceholder.
  ///
  /// In en, this message translates to:
  /// **'Add details…'**
  String get tasksDescriptionPlaceholder;

  /// No description provided for @tasksEdit.
  ///
  /// In en, this message translates to:
  /// **'Edit'**
  String get tasksEdit;

  /// No description provided for @tasksEditTask.
  ///
  /// In en, this message translates to:
  /// **'Edit task'**
  String get tasksEditTask;

  /// No description provided for @tasksLabelsFieldLabel.
  ///
  /// In en, this message translates to:
  /// **'LABELS'**
  String get tasksLabelsFieldLabel;

  /// No description provided for @tasksNewTask.
  ///
  /// In en, this message translates to:
  /// **'New task'**
  String get tasksNewTask;

  /// No description provided for @tasksDisplay.
  ///
  /// In en, this message translates to:
  /// **'Display'**
  String get tasksDisplay;

  /// No description provided for @tasksInbox.
  ///
  /// In en, this message translates to:
  /// **'Inbox'**
  String get tasksInbox;

  /// No description provided for @tasksLabelsButton.
  ///
  /// In en, this message translates to:
  /// **'Labels'**
  String get tasksLabelsButton;

  /// No description provided for @tasksPropPriority.
  ///
  /// In en, this message translates to:
  /// **'Priority'**
  String get tasksPropPriority;

  /// No description provided for @tasksPropProject.
  ///
  /// In en, this message translates to:
  /// **'Project'**
  String get tasksPropProject;

  /// No description provided for @tasksPropStatus.
  ///
  /// In en, this message translates to:
  /// **'Status'**
  String get tasksPropStatus;

  /// No description provided for @tasksNoTasksSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Create a task to plan work you can hand to an agent.'**
  String get tasksNoTasksSubtitle;

  /// No description provided for @tasksNoTasksTitle.
  ///
  /// In en, this message translates to:
  /// **'No tasks yet'**
  String get tasksNoTasksTitle;

  /// No description provided for @tasksPriorityFieldLabel.
  ///
  /// In en, this message translates to:
  /// **'PRIORITY'**
  String get tasksPriorityFieldLabel;

  /// No description provided for @tasksPriorityHigh.
  ///
  /// In en, this message translates to:
  /// **'High'**
  String get tasksPriorityHigh;

  /// No description provided for @tasksPriorityLow.
  ///
  /// In en, this message translates to:
  /// **'Low'**
  String get tasksPriorityLow;

  /// No description provided for @tasksPriorityMedium.
  ///
  /// In en, this message translates to:
  /// **'Medium'**
  String get tasksPriorityMedium;

  /// No description provided for @tasksPriorityNone.
  ///
  /// In en, this message translates to:
  /// **'No priority'**
  String get tasksPriorityNone;

  /// No description provided for @tasksPriorityUrgent.
  ///
  /// In en, this message translates to:
  /// **'Urgent'**
  String get tasksPriorityUrgent;

  /// No description provided for @tasksProjectFieldLabel.
  ///
  /// In en, this message translates to:
  /// **'PROJECT'**
  String get tasksProjectFieldLabel;

  /// No description provided for @tasksPullToRefresh.
  ///
  /// In en, this message translates to:
  /// **'Pull to refresh'**
  String get tasksPullToRefresh;

  /// No description provided for @tasksSave.
  ///
  /// In en, this message translates to:
  /// **'Save'**
  String get tasksSave;

  /// No description provided for @tasksSaveFailed.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t save task. Please try again.'**
  String get tasksSaveFailed;

  /// No description provided for @tasksStartSession.
  ///
  /// In en, this message translates to:
  /// **'Start session'**
  String get tasksStartSession;

  /// No description provided for @tasksSubtasks.
  ///
  /// In en, this message translates to:
  /// **'Sub-tasks'**
  String get tasksSubtasks;

  /// No description provided for @tasksStatusBacklog.
  ///
  /// In en, this message translates to:
  /// **'Backlog'**
  String get tasksStatusBacklog;

  /// No description provided for @tasksStatusBlocked.
  ///
  /// In en, this message translates to:
  /// **'Blocked'**
  String get tasksStatusBlocked;

  /// No description provided for @tasksStatusCancelled.
  ///
  /// In en, this message translates to:
  /// **'Cancelled'**
  String get tasksStatusCancelled;

  /// No description provided for @tasksStatusDone.
  ///
  /// In en, this message translates to:
  /// **'Done'**
  String get tasksStatusDone;

  /// No description provided for @tasksStatusFieldLabel.
  ///
  /// In en, this message translates to:
  /// **'STATUS'**
  String get tasksStatusFieldLabel;

  /// No description provided for @tasksStatusInProgress.
  ///
  /// In en, this message translates to:
  /// **'In Progress'**
  String get tasksStatusInProgress;

  /// No description provided for @tasksStatusInReview.
  ///
  /// In en, this message translates to:
  /// **'In Review'**
  String get tasksStatusInReview;

  /// No description provided for @tasksStatusTodo.
  ///
  /// In en, this message translates to:
  /// **'Todo'**
  String get tasksStatusTodo;

  /// No description provided for @tasksTaskDeleted.
  ///
  /// In en, this message translates to:
  /// **'Task deleted'**
  String get tasksTaskDeleted;

  /// No description provided for @tasksTitle.
  ///
  /// In en, this message translates to:
  /// **'Tasks'**
  String get tasksTitle;

  /// No description provided for @tasksTitleFieldLabel.
  ///
  /// In en, this message translates to:
  /// **'TITLE'**
  String get tasksTitleFieldLabel;

  /// No description provided for @tasksTitlePlaceholder.
  ///
  /// In en, this message translates to:
  /// **'What needs to be done?'**
  String get tasksTitlePlaceholder;

  /// No description provided for @tasksTitleRequired.
  ///
  /// In en, this message translates to:
  /// **'Title is required'**
  String get tasksTitleRequired;

  /// No description provided for @accountCautionZone.
  ///
  /// In en, this message translates to:
  /// **'CAUTION ZONE'**
  String get accountCautionZone;

  /// No description provided for @accountDeleteAccount.
  ///
  /// In en, this message translates to:
  /// **'Delete Account'**
  String get accountDeleteAccount;

  /// No description provided for @accountDeleteDialogBody.
  ///
  /// In en, this message translates to:
  /// **'All your data will be permanently deleted. Are you sure to proceed?'**
  String get accountDeleteDialogBody;

  /// No description provided for @accountDeleteDialogTitle.
  ///
  /// In en, this message translates to:
  /// **'Delete Account?'**
  String get accountDeleteDialogTitle;

  /// No description provided for @accountEmail.
  ///
  /// In en, this message translates to:
  /// **'Email'**
  String get accountEmail;

  /// No description provided for @accountLogOut.
  ///
  /// In en, this message translates to:
  /// **'Log Out'**
  String get accountLogOut;

  /// No description provided for @accountName.
  ///
  /// In en, this message translates to:
  /// **'Name'**
  String get accountName;

  /// No description provided for @accountNameHint.
  ///
  /// In en, this message translates to:
  /// **'Guest'**
  String get accountNameHint;

  /// No description provided for @accountRegistration.
  ///
  /// In en, this message translates to:
  /// **'Registration'**
  String get accountRegistration;

  /// No description provided for @accountTitle.
  ///
  /// In en, this message translates to:
  /// **'Account'**
  String get accountTitle;

  /// No description provided for @addToChatChooseFiles.
  ///
  /// In en, this message translates to:
  /// **'Files'**
  String get addToChatChooseFiles;

  /// No description provided for @addToChatCommands.
  ///
  /// In en, this message translates to:
  /// **'Commands'**
  String get addToChatCommands;

  /// No description provided for @addToChatPhotoLibrary.
  ///
  /// In en, this message translates to:
  /// **'Photo'**
  String get addToChatPhotoLibrary;

  /// No description provided for @addToChatSkillsOrCommands.
  ///
  /// In en, this message translates to:
  /// **'Skills or Commands'**
  String get addToChatSkillsOrCommands;

  /// No description provided for @addToChatTakePhoto.
  ///
  /// In en, this message translates to:
  /// **'Camera'**
  String get addToChatTakePhoto;

  /// No description provided for @agentCatalogReasoningLabel.
  ///
  /// In en, this message translates to:
  /// **'Reasoning - {label}'**
  String agentCatalogReasoningLabel(Object label);

  /// No description provided for @agentCatalogThinkingLabel.
  ///
  /// In en, this message translates to:
  /// **'Thinking - {label}'**
  String agentCatalogThinkingLabel(Object label);

  /// No description provided for @agentChatAddToChat.
  ///
  /// In en, this message translates to:
  /// **'Add to chat'**
  String get agentChatAddToChat;

  /// No description provided for @agentChatAgentMode.
  ///
  /// In en, this message translates to:
  /// **'Agent Mode'**
  String get agentChatAgentMode;

  /// No description provided for @agentChatCancelQueuedMessageTooltip.
  ///
  /// In en, this message translates to:
  /// **'Cancel message'**
  String get agentChatCancelQueuedMessageTooltip;

  /// No description provided for @agentChatRevertQueuedMessageTooltip.
  ///
  /// In en, this message translates to:
  /// **'Edit in input'**
  String get agentChatRevertQueuedMessageTooltip;

  /// No description provided for @agentChatCancelledLabel.
  ///
  /// In en, this message translates to:
  /// **'Cancelled'**
  String get agentChatCancelledLabel;

  /// No description provided for @agentChatCloseFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to archive session. Please try again.'**
  String get agentChatCloseFailed;

  /// No description provided for @agentChatCopiedToClipboard.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Copied 1 message to clipboard} other{Copied {count} messages to clipboard}}'**
  String agentChatCopiedToClipboard(int count);

  /// No description provided for @agentChatCopyFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to copy messages'**
  String get agentChatCopyFailed;

  /// No description provided for @agentChatCopyResponse.
  ///
  /// In en, this message translates to:
  /// **'Copy response'**
  String get agentChatCopyResponse;

  /// No description provided for @agentChatDeleteFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to delete session. Please try again.'**
  String get agentChatDeleteFailed;

  /// No description provided for @agentChatErrorLoadingMessages.
  ///
  /// In en, this message translates to:
  /// **'Error Loading Messages'**
  String get agentChatErrorLoadingMessages;

  /// No description provided for @agentChatInitFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to initialize chat'**
  String get agentChatInitFailed;

  /// No description provided for @agentChatMentionFiles.
  ///
  /// In en, this message translates to:
  /// **'Mention files'**
  String get agentChatMentionFiles;

  /// No description provided for @agentChatNewMessagesCount.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{{count} message} other{{count} messages}}'**
  String agentChatNewMessagesCount(int count);

  /// No description provided for @agentChatNoMessagesSelected.
  ///
  /// In en, this message translates to:
  /// **'No messages selected'**
  String get agentChatNoMessagesSelected;

  /// No description provided for @agentChatNoMessagesToShare.
  ///
  /// In en, this message translates to:
  /// **'No messages to share'**
  String get agentChatNoMessagesToShare;

  /// No description provided for @agentChatPermissionMode.
  ///
  /// In en, this message translates to:
  /// **'Permission Mode'**
  String get agentChatPermissionMode;

  /// No description provided for @agentChatPinFailed.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t pin session'**
  String get agentChatPinFailed;

  /// No description provided for @agentChatQueuedCount.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 queued} other{{count} queued}}'**
  String agentChatQueuedCount(int count);

  /// No description provided for @agentChatQueuedLabel.
  ///
  /// In en, this message translates to:
  /// **'Queued'**
  String get agentChatQueuedLabel;

  /// No description provided for @agentChatQueuedSheetTitle.
  ///
  /// In en, this message translates to:
  /// **'Queued messages'**
  String get agentChatQueuedSheetTitle;

  /// No description provided for @agentChatRenameFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to rename session. Please try again.'**
  String get agentChatRenameFailed;

  /// No description provided for @agentChatSessionReady.
  ///
  /// In en, this message translates to:
  /// **'Session ready'**
  String get agentChatSessionReady;

  /// No description provided for @agentChatSessionRenamed.
  ///
  /// In en, this message translates to:
  /// **'Session renamed successfully'**
  String get agentChatSessionRenamed;

  /// No description provided for @agentChatSessionTitle.
  ///
  /// In en, this message translates to:
  /// **'Session'**
  String get agentChatSessionTitle;

  /// No description provided for @agentChatShareFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to share messages'**
  String get agentChatShareFailed;

  /// No description provided for @agentChatShareResponse.
  ///
  /// In en, this message translates to:
  /// **'Share response'**
  String get agentChatShareResponse;

  /// No description provided for @agentChatShowSlashCommands.
  ///
  /// In en, this message translates to:
  /// **'Show slash commands'**
  String get agentChatShowSlashCommands;

  /// No description provided for @agentChatStartingYourSession.
  ///
  /// In en, this message translates to:
  /// **'Starting your session'**
  String get agentChatStartingYourSession;

  /// No description provided for @agentChatThinking.
  ///
  /// In en, this message translates to:
  /// **'Thinking'**
  String get agentChatThinking;

  /// No description provided for @agentChatThinkingOff.
  ///
  /// In en, this message translates to:
  /// **'Off'**
  String get agentChatThinkingOff;

  /// No description provided for @agentChatThinkingOn.
  ///
  /// In en, this message translates to:
  /// **'On'**
  String get agentChatThinkingOn;

  /// No description provided for @agentChatTranscribing.
  ///
  /// In en, this message translates to:
  /// **'Transcribing...'**
  String get agentChatTranscribing;

  /// No description provided for @agentChatUnexpectedError.
  ///
  /// In en, this message translates to:
  /// **'An unexpected error occurred'**
  String get agentChatUnexpectedError;

  /// No description provided for @agentChatUnpinFailed.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t unpin session'**
  String get agentChatUnpinFailed;

  /// No description provided for @agentChatWaitingForMessages.
  ///
  /// In en, this message translates to:
  /// **'Waiting for messages'**
  String get agentChatWaitingForMessages;

  /// No description provided for @agentConfigAgent.
  ///
  /// In en, this message translates to:
  /// **'Agent'**
  String get agentConfigAgent;

  /// No description provided for @agentConfigBetaLabel.
  ///
  /// In en, this message translates to:
  /// **'{label} (Beta)'**
  String agentConfigBetaLabel(Object label);

  /// No description provided for @agentConfigMode.
  ///
  /// In en, this message translates to:
  /// **'Mode'**
  String get agentConfigMode;

  /// No description provided for @agentConfigModel.
  ///
  /// In en, this message translates to:
  /// **'Model'**
  String get agentConfigModel;

  /// No description provided for @agentConfigNotInstalled.
  ///
  /// In en, this message translates to:
  /// **'Not installed'**
  String get agentConfigNotInstalled;

  /// No description provided for @agentConfigNotInstalledPrefix.
  ///
  /// In en, this message translates to:
  /// **'{label} is not installed on this machine. Install it, then restart '**
  String agentConfigNotInstalledPrefix(Object label);

  /// No description provided for @agentConfigNotInstalledSuffix.
  ///
  /// In en, this message translates to:
  /// **' to use it.'**
  String get agentConfigNotInstalledSuffix;

  /// No description provided for @agentConfigPanelAgent.
  ///
  /// In en, this message translates to:
  /// **'Agent'**
  String get agentConfigPanelAgent;

  /// No description provided for @agentConfigPanelMode.
  ///
  /// In en, this message translates to:
  /// **'Mode'**
  String get agentConfigPanelMode;

  /// No description provided for @agentConfigPanelModel.
  ///
  /// In en, this message translates to:
  /// **'Model'**
  String get agentConfigPanelModel;

  /// No description provided for @agentConfigPanelPermission.
  ///
  /// In en, this message translates to:
  /// **'Permission'**
  String get agentConfigPanelPermission;

  /// No description provided for @agentConfigPanelReasoning.
  ///
  /// In en, this message translates to:
  /// **'Reasoning'**
  String get agentConfigPanelReasoning;

  /// No description provided for @agentConfigPanelThinking.
  ///
  /// In en, this message translates to:
  /// **'Thinking'**
  String get agentConfigPanelThinking;

  /// No description provided for @agentConfigPanelUnknownAgent.
  ///
  /// In en, this message translates to:
  /// **'Unknown agent — update the app to configure this.'**
  String get agentConfigPanelUnknownAgent;

  /// No description provided for @agentConfigPermission.
  ///
  /// In en, this message translates to:
  /// **'Permission'**
  String get agentConfigPermission;

  /// No description provided for @agentConfigReasoningEffort.
  ///
  /// In en, this message translates to:
  /// **'Reasoning Effort'**
  String get agentConfigReasoningEffort;

  /// No description provided for @agentConfigThinkingEffort.
  ///
  /// In en, this message translates to:
  /// **'Thinking Effort'**
  String get agentConfigThinkingEffort;

  /// No description provided for @agentConfigUnknownAgent.
  ///
  /// In en, this message translates to:
  /// **'Unknown agent — update the app to configure this.'**
  String get agentConfigUnknownAgent;

  /// No description provided for @appLanguageTitle.
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get appLanguageTitle;

  /// No description provided for @appearanceChat.
  ///
  /// In en, this message translates to:
  /// **'Chat'**
  String get appearanceChat;

  /// No description provided for @appearanceCodeBlock.
  ///
  /// In en, this message translates to:
  /// **'Code Block'**
  String get appearanceCodeBlock;

  /// No description provided for @appearanceCollapseLongCode.
  ///
  /// In en, this message translates to:
  /// **'Collapse Long Code'**
  String get appearanceCollapseLongCode;

  /// No description provided for @appearanceCollapseToolCalls.
  ///
  /// In en, this message translates to:
  /// **'Collapse Tool Calls'**
  String get appearanceCollapseToolCalls;

  /// Label for the dark/light theme toggle
  ///
  /// In en, this message translates to:
  /// **'Dark Mode'**
  String get appearanceDarkMode;

  /// Label for the app UI language selector
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get appearanceLanguage;

  /// No description provided for @appearanceLinesBeforeCollapsing.
  ///
  /// In en, this message translates to:
  /// **'Lines before collapsing'**
  String get appearanceLinesBeforeCollapsing;

  /// No description provided for @appearanceShowFilter.
  ///
  /// In en, this message translates to:
  /// **'Show Filter'**
  String get appearanceShowFilter;

  /// No description provided for @appearanceShowLivePreview.
  ///
  /// In en, this message translates to:
  /// **'Show Live Preview'**
  String get appearanceShowLivePreview;

  /// Title of the Appearance settings page
  ///
  /// In en, this message translates to:
  /// **'Appearance'**
  String get appearanceTitle;

  /// No description provided for @askUserQuestionPanelCancelling.
  ///
  /// In en, this message translates to:
  /// **'Cancelling...'**
  String get askUserQuestionPanelCancelling;

  /// No description provided for @askUserQuestionPanelQuestionNumber.
  ///
  /// In en, this message translates to:
  /// **'Question {number}'**
  String askUserQuestionPanelQuestionNumber(Object number);

  /// No description provided for @askUserQuestionPanelSubmit.
  ///
  /// In en, this message translates to:
  /// **'Submit'**
  String get askUserQuestionPanelSubmit;

  /// No description provided for @askUserQuestionPanelSubmitting.
  ///
  /// In en, this message translates to:
  /// **'Submitting...'**
  String get askUserQuestionPanelSubmitting;

  /// No description provided for @askUserQuestionPanelTypeSomething.
  ///
  /// In en, this message translates to:
  /// **'Type something'**
  String get askUserQuestionPanelTypeSomething;

  /// No description provided for @askUserQuestionPanelTypeYourAnswer.
  ///
  /// In en, this message translates to:
  /// **'Type your answer'**
  String get askUserQuestionPanelTypeYourAnswer;

  /// No description provided for @authEmailChangeConfirmationSent.
  ///
  /// In en, this message translates to:
  /// **'Email change confirmation email sent'**
  String get authEmailChangeConfirmationSent;

  /// No description provided for @authOptionsAndConnector.
  ///
  /// In en, this message translates to:
  /// **' and '**
  String get authOptionsAndConnector;

  /// No description provided for @authOptionsContinueWithApple.
  ///
  /// In en, this message translates to:
  /// **'Continue with Apple'**
  String get authOptionsContinueWithApple;

  /// No description provided for @authOptionsContinueWithEmail.
  ///
  /// In en, this message translates to:
  /// **'Continue with Email'**
  String get authOptionsContinueWithEmail;

  /// No description provided for @authOptionsContinueWithGoogle.
  ///
  /// In en, this message translates to:
  /// **'Continue with Google'**
  String get authOptionsContinueWithGoogle;

  /// No description provided for @authOptionsLegalPrefix.
  ///
  /// In en, this message translates to:
  /// **'By continuing, you agree to the\n'**
  String get authOptionsLegalPrefix;

  /// No description provided for @authOptionsPrivacyPolicy.
  ///
  /// In en, this message translates to:
  /// **'privacy policy'**
  String get authOptionsPrivacyPolicy;

  /// No description provided for @authOptionsSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Run a team of coding agents from your phone'**
  String get authOptionsSubtitle;

  /// No description provided for @authOptionsTermsOfUse.
  ///
  /// In en, this message translates to:
  /// **'terms of use'**
  String get authOptionsTermsOfUse;

  /// No description provided for @authOptionsTitle.
  ///
  /// In en, this message translates to:
  /// **'Let\'s Get Started'**
  String get authOptionsTitle;

  /// No description provided for @billingXNoOffering.
  ///
  /// In en, this message translates to:
  /// **'No offering available'**
  String get billingXNoOffering;

  /// No description provided for @billingXPaywallLoadError.
  ///
  /// In en, this message translates to:
  /// **'Error loading paywall: {error}'**
  String billingXPaywallLoadError(Object error);

  /// No description provided for @chatErrorLoadMessagesFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to load messages. Please check your connection.'**
  String get chatErrorLoadMessagesFailed;

  /// No description provided for @chatInputAddToChat.
  ///
  /// In en, this message translates to:
  /// **'Add to chat'**
  String get chatInputAddToChat;

  /// No description provided for @chatInputBrowseFiles.
  ///
  /// In en, this message translates to:
  /// **'Browse files'**
  String get chatInputBrowseFiles;

  /// No description provided for @chatInputCliOutdated.
  ///
  /// In en, this message translates to:
  /// **'Vicoa CLI could be outdated. Upgrade it to access files and changes.'**
  String get chatInputCliOutdated;

  /// No description provided for @chatInputModelConfig.
  ///
  /// In en, this message translates to:
  /// **'Model Config'**
  String get chatInputModelConfig;

  /// No description provided for @chatInputOpenWebPreview.
  ///
  /// In en, this message translates to:
  /// **'Open web preview'**
  String get chatInputOpenWebPreview;

  /// No description provided for @chatInputPlaceholder.
  ///
  /// In en, this message translates to:
  /// **'Type messages, @files, /skills or commands'**
  String get chatInputPlaceholder;

  /// No description provided for @chatInputSessionConfig.
  ///
  /// In en, this message translates to:
  /// **'Session Config'**
  String get chatInputSessionConfig;

  /// No description provided for @chatInputSessionEnded.
  ///
  /// In en, this message translates to:
  /// **'Session archived. Chat is closed here'**
  String get chatInputSessionEnded;

  /// No description provided for @chatInputSessionReadOnly.
  ///
  /// In en, this message translates to:
  /// **'Session is archived. Configs are read-only.'**
  String get chatInputSessionReadOnly;

  /// No description provided for @chatInputStopTask.
  ///
  /// In en, this message translates to:
  /// **'Stop current task'**
  String get chatInputStopTask;

  /// No description provided for @chatOptionsInfo.
  ///
  /// In en, this message translates to:
  /// **'Info'**
  String get chatOptionsInfo;

  /// No description provided for @chatOptionsPin.
  ///
  /// In en, this message translates to:
  /// **'Pin'**
  String get chatOptionsPin;

  /// No description provided for @chatOptionsRename.
  ///
  /// In en, this message translates to:
  /// **'Rename'**
  String get chatOptionsRename;

  /// No description provided for @chatOptionsUnpin.
  ///
  /// In en, this message translates to:
  /// **'Unpin'**
  String get chatOptionsUnpin;

  /// No description provided for @commonBack.
  ///
  /// In en, this message translates to:
  /// **'Back'**
  String get commonBack;

  /// No description provided for @commonCancel.
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get commonCancel;

  /// No description provided for @commonClose.
  ///
  /// In en, this message translates to:
  /// **'Close'**
  String get commonClose;

  /// No description provided for @commonConfirm.
  ///
  /// In en, this message translates to:
  /// **'Confirm'**
  String get commonConfirm;

  /// No description provided for @commonContinue.
  ///
  /// In en, this message translates to:
  /// **'Continue'**
  String get commonContinue;

  /// No description provided for @commonCopied.
  ///
  /// In en, this message translates to:
  /// **'Copied'**
  String get commonCopied;

  /// No description provided for @commonCopy.
  ///
  /// In en, this message translates to:
  /// **'Copy'**
  String get commonCopy;

  /// No description provided for @commonDelete.
  ///
  /// In en, this message translates to:
  /// **'Delete'**
  String get commonDelete;

  /// No description provided for @commonDone.
  ///
  /// In en, this message translates to:
  /// **'Done'**
  String get commonDone;

  /// No description provided for @commonEdit.
  ///
  /// In en, this message translates to:
  /// **'Edit'**
  String get commonEdit;

  /// No description provided for @commonError.
  ///
  /// In en, this message translates to:
  /// **'Error'**
  String get commonError;

  /// No description provided for @commonLoading.
  ///
  /// In en, this message translates to:
  /// **'Loading…'**
  String get commonLoading;

  /// No description provided for @commonNext.
  ///
  /// In en, this message translates to:
  /// **'Next'**
  String get commonNext;

  /// No description provided for @commonNo.
  ///
  /// In en, this message translates to:
  /// **'No'**
  String get commonNo;

  /// No description provided for @commonOk.
  ///
  /// In en, this message translates to:
  /// **'OK'**
  String get commonOk;

  /// No description provided for @commonRemove.
  ///
  /// In en, this message translates to:
  /// **'Remove'**
  String get commonRemove;

  /// No description provided for @commonRetry.
  ///
  /// In en, this message translates to:
  /// **'Retry'**
  String get commonRetry;

  /// No description provided for @commonSave.
  ///
  /// In en, this message translates to:
  /// **'Save'**
  String get commonSave;

  /// No description provided for @commonSearch.
  ///
  /// In en, this message translates to:
  /// **'Search'**
  String get commonSearch;

  /// No description provided for @commonSettings.
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get commonSettings;

  /// No description provided for @commonShare.
  ///
  /// In en, this message translates to:
  /// **'Share'**
  String get commonShare;

  /// No description provided for @commonSignIn.
  ///
  /// In en, this message translates to:
  /// **'Sign In'**
  String get commonSignIn;

  /// No description provided for @commonSignOut.
  ///
  /// In en, this message translates to:
  /// **'Sign Out'**
  String get commonSignOut;

  /// No description provided for @commonSignUp.
  ///
  /// In en, this message translates to:
  /// **'Sign Up'**
  String get commonSignUp;

  /// No description provided for @commonSkip.
  ///
  /// In en, this message translates to:
  /// **'Skip'**
  String get commonSkip;

  /// No description provided for @commonYes.
  ///
  /// In en, this message translates to:
  /// **'Yes'**
  String get commonYes;

  /// No description provided for @configureSetupConfiguringBest.
  ///
  /// In en, this message translates to:
  /// **'Your AI agent\nis almost ready'**
  String get configureSetupConfiguringBest;

  /// No description provided for @configureSetupJustAMoment.
  ///
  /// In en, this message translates to:
  /// **'Just a moment...'**
  String get configureSetupJustAMoment;

  /// No description provided for @configureSetupSocialProof.
  ///
  /// In en, this message translates to:
  /// **'People who use Vicoa have built faster with \nAI coding agents anywhere they go.'**
  String get configureSetupSocialProof;

  /// No description provided for @confirmDialogAreYouSure.
  ///
  /// In en, this message translates to:
  /// **'Are you sure?'**
  String get confirmDialogAreYouSure;

  /// No description provided for @confirmRatingBody.
  ///
  /// In en, this message translates to:
  /// **'Thank you for supporting us! \n\nIf you\'ve gave us a happy 5 stars, tap the button below to claim your free messages.'**
  String get confirmRatingBody;

  /// No description provided for @confirmRatingDoneButton.
  ///
  /// In en, this message translates to:
  /// **'I Have Done It'**
  String get confirmRatingDoneButton;

  /// No description provided for @confirmRatingGiftButton.
  ///
  /// In en, this message translates to:
  /// **'Continue to Use'**
  String get confirmRatingGiftButton;

  /// No description provided for @confirmRatingGiftText.
  ///
  /// In en, this message translates to:
  /// **'Yay! You got 50 free messages!'**
  String get confirmRatingGiftText;

  /// No description provided for @confirmRatingTitle.
  ///
  /// In en, this message translates to:
  /// **'Give us a Happy 5 Stars!'**
  String get confirmRatingTitle;

  /// No description provided for @connectComputerLinkCopied.
  ///
  /// In en, this message translates to:
  /// **'Link copied'**
  String get connectComputerLinkCopied;

  /// No description provided for @connectComputerLoginSameAccount.
  ///
  /// In en, this message translates to:
  /// **'Download the desktop app and sign in with the same account. Your computer connects automatically.'**
  String get connectComputerLoginSameAccount;

  /// No description provided for @connectComputerTitle.
  ///
  /// In en, this message translates to:
  /// **'Connect Your Computer'**
  String get connectComputerTitle;

  /// No description provided for @connectComputerViewDocs.
  ///
  /// In en, this message translates to:
  /// **'View full documentation'**
  String get connectComputerViewDocs;

  /// No description provided for @credtiHistoryTitle.
  ///
  /// In en, this message translates to:
  /// **'Credit History'**
  String get credtiHistoryTitle;

  /// No description provided for @dateRangeXApply.
  ///
  /// In en, this message translates to:
  /// **'Apply'**
  String get dateRangeXApply;

  /// No description provided for @dateRangeXEndDate.
  ///
  /// In en, this message translates to:
  /// **'End Date'**
  String get dateRangeXEndDate;

  /// No description provided for @dateRangeXStartDate.
  ///
  /// In en, this message translates to:
  /// **'Start Date'**
  String get dateRangeXStartDate;

  /// No description provided for @dateRangeXTitle.
  ///
  /// In en, this message translates to:
  /// **'Custom Date Range'**
  String get dateRangeXTitle;

  /// No description provided for @dateRangeXWeekdayFri.
  ///
  /// In en, this message translates to:
  /// **'Fri'**
  String get dateRangeXWeekdayFri;

  /// No description provided for @dateRangeXWeekdayMon.
  ///
  /// In en, this message translates to:
  /// **'Mon'**
  String get dateRangeXWeekdayMon;

  /// No description provided for @dateRangeXWeekdaySat.
  ///
  /// In en, this message translates to:
  /// **'Sat'**
  String get dateRangeXWeekdaySat;

  /// No description provided for @dateRangeXWeekdaySun.
  ///
  /// In en, this message translates to:
  /// **'Sun'**
  String get dateRangeXWeekdaySun;

  /// No description provided for @dateRangeXWeekdayThu.
  ///
  /// In en, this message translates to:
  /// **'Thu'**
  String get dateRangeXWeekdayThu;

  /// No description provided for @dateRangeXWeekdayTue.
  ///
  /// In en, this message translates to:
  /// **'Tue'**
  String get dateRangeXWeekdayTue;

  /// No description provided for @dateRangeXWeekdayWed.
  ///
  /// In en, this message translates to:
  /// **'Wed'**
  String get dateRangeXWeekdayWed;

  /// No description provided for @dateToday.
  ///
  /// In en, this message translates to:
  /// **'Today'**
  String get dateToday;

  /// No description provided for @dateYesterday.
  ///
  /// In en, this message translates to:
  /// **'Yesterday'**
  String get dateYesterday;

  /// No description provided for @directoryPickerRecent.
  ///
  /// In en, this message translates to:
  /// **'Recent'**
  String get directoryPickerRecent;

  /// No description provided for @directoryPickerWorkingDirectory.
  ///
  /// In en, this message translates to:
  /// **'Working Directory'**
  String get directoryPickerWorkingDirectory;

  /// No description provided for @errorStateDisplaySignInAgain.
  ///
  /// In en, this message translates to:
  /// **'Sign In Again'**
  String get errorStateDisplaySignInAgain;

  /// No description provided for @errorStateDisplayTryAgain.
  ///
  /// In en, this message translates to:
  /// **'Try Again'**
  String get errorStateDisplayTryAgain;

  /// No description provided for @errorStateDisplayUnexpectedError.
  ///
  /// In en, this message translates to:
  /// **'An unexpected error occurred'**
  String get errorStateDisplayUnexpectedError;

  /// No description provided for @fileViewerXAddToContext.
  ///
  /// In en, this message translates to:
  /// **'Add to context'**
  String get fileViewerXAddToContext;

  /// No description provided for @fileViewerXBinaryFile.
  ///
  /// In en, this message translates to:
  /// **'Binary file ({size})'**
  String fileViewerXBinaryFile(Object size);

  /// No description provided for @fileViewerXDetailNotDownloaded.
  ///
  /// In en, this message translates to:
  /// **'file is not downloaded'**
  String get fileViewerXDetailNotDownloaded;

  /// No description provided for @fileViewerXDetailOutdated.
  ///
  /// In en, this message translates to:
  /// **'file could be outdated'**
  String get fileViewerXDetailOutdated;

  /// No description provided for @fileViewerXErrDefault.
  ///
  /// In en, this message translates to:
  /// **'Couldn’t load this file ({code}).'**
  String fileViewerXErrDefault(Object code);

  /// No description provided for @fileViewerXErrMachineOffline.
  ///
  /// In en, this message translates to:
  /// **'Machine is offline.'**
  String get fileViewerXErrMachineOffline;

  /// No description provided for @fileViewerXErrNoHandler.
  ///
  /// In en, this message translates to:
  /// **'Update the daemon on this machine — older version doesn’t support file viewing.'**
  String get fileViewerXErrNoHandler;

  /// No description provided for @fileViewerXErrNotAFile.
  ///
  /// In en, this message translates to:
  /// **'Not a file.'**
  String get fileViewerXErrNotAFile;

  /// No description provided for @fileViewerXErrOutsideProject.
  ///
  /// In en, this message translates to:
  /// **'Path is outside the project.'**
  String get fileViewerXErrOutsideProject;

  /// No description provided for @fileViewerXErrPathNotFound.
  ///
  /// In en, this message translates to:
  /// **'This file no longer exists.'**
  String get fileViewerXErrPathNotFound;

  /// No description provided for @fileViewerXErrPermissionDenied.
  ///
  /// In en, this message translates to:
  /// **'Permission denied.'**
  String get fileViewerXErrPermissionDenied;

  /// No description provided for @fileViewerXErrTimeout.
  ///
  /// In en, this message translates to:
  /// **'The machine took too long to respond.'**
  String get fileViewerXErrTimeout;

  /// No description provided for @fileViewerXFileNotDownloaded.
  ///
  /// In en, this message translates to:
  /// **'File not downloaded on this device.'**
  String get fileViewerXFileNotDownloaded;

  /// No description provided for @fileViewerXImageTooLarge.
  ///
  /// In en, this message translates to:
  /// **'Image too large to preview on mobile.'**
  String get fileViewerXImageTooLarge;

  /// No description provided for @fileViewerXPreviewNotAvailable.
  ///
  /// In en, this message translates to:
  /// **'Preview not available.'**
  String get fileViewerXPreviewNotAvailable;

  /// No description provided for @fileViewerXReconnectToView.
  ///
  /// In en, this message translates to:
  /// **'Reconnect the machine to view it.'**
  String get fileViewerXReconnectToView;

  /// No description provided for @fileViewerXRefresh.
  ///
  /// In en, this message translates to:
  /// **'Refresh'**
  String get fileViewerXRefresh;

  /// No description provided for @fileViewerXShowingFirstPortion.
  ///
  /// In en, this message translates to:
  /// **'Showing first portion of {size}. Open on desktop to see the rest.'**
  String fileViewerXShowingFirstPortion(Object size);

  /// No description provided for @filesGitXBinaryFileChanged.
  ///
  /// In en, this message translates to:
  /// **'Binary file changed · {size}'**
  String filesGitXBinaryFileChanged(Object size);

  /// No description provided for @filesGitXCollapseAllTooltip.
  ///
  /// In en, this message translates to:
  /// **'Collapse all'**
  String get filesGitXCollapseAllTooltip;

  /// No description provided for @filesGitXCouldntLoadDiff.
  ///
  /// In en, this message translates to:
  /// **'Couldn’t load diff — {code}'**
  String filesGitXCouldntLoadDiff(Object code);

  /// No description provided for @filesGitXCouldntLoadStatus.
  ///
  /// In en, this message translates to:
  /// **'Couldn’t load status'**
  String get filesGitXCouldntLoadStatus;

  /// No description provided for @filesGitXDetachedAt.
  ///
  /// In en, this message translates to:
  /// **'(detached at {branch})'**
  String filesGitXDetachedAt(Object branch);

  /// No description provided for @filesGitXDiffTruncated.
  ///
  /// In en, this message translates to:
  /// **'Diff truncated — open on desktop for the rest.'**
  String get filesGitXDiffTruncated;

  /// No description provided for @filesGitXExpandAllTooltip.
  ///
  /// In en, this message translates to:
  /// **'Expand all'**
  String get filesGitXExpandAllTooltip;

  /// No description provided for @filesGitXHideWhitespaceTooltip.
  ///
  /// In en, this message translates to:
  /// **'Hide whitespace'**
  String get filesGitXHideWhitespaceTooltip;

  /// No description provided for @filesGitXNoChangesVsHead.
  ///
  /// In en, this message translates to:
  /// **'No changes vs HEAD.'**
  String get filesGitXNoChangesVsHead;

  /// No description provided for @filesGitXNoUpstream.
  ///
  /// In en, this message translates to:
  /// **'  ·  no upstream'**
  String get filesGitXNoUpstream;

  /// No description provided for @filesGitXNotARepoSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Open this directory in a git project to see changes.'**
  String get filesGitXNotARepoSubtitle;

  /// No description provided for @filesGitXNotARepoTitle.
  ///
  /// In en, this message translates to:
  /// **'Not a git repository'**
  String get filesGitXNotARepoTitle;

  /// No description provided for @filesGitXReconnectToSeeChanges.
  ///
  /// In en, this message translates to:
  /// **'Reconnect the machine to see changes.'**
  String get filesGitXReconnectToSeeChanges;

  /// No description provided for @filesGitXRefreshTooltip.
  ///
  /// In en, this message translates to:
  /// **'Refresh'**
  String get filesGitXRefreshTooltip;

  /// No description provided for @filesGitXSectionLabel.
  ///
  /// In en, this message translates to:
  /// **'{label} · {count}'**
  String filesGitXSectionLabel(Object label, Object count);

  /// No description provided for @filesGitXSectionStaged.
  ///
  /// In en, this message translates to:
  /// **'Staged'**
  String get filesGitXSectionStaged;

  /// No description provided for @filesGitXSectionUnstaged.
  ///
  /// In en, this message translates to:
  /// **'Unstaged'**
  String get filesGitXSectionUnstaged;

  /// No description provided for @filesGitXSectionUntracked.
  ///
  /// In en, this message translates to:
  /// **'Untracked'**
  String get filesGitXSectionUntracked;

  /// No description provided for @filesGitXShowMoreLines.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Show {count} more line} other{Show {count} more lines}}'**
  String filesGitXShowMoreLines(int count);

  /// No description provided for @filesGitXShowWhitespaceTooltip.
  ///
  /// In en, this message translates to:
  /// **'Show whitespace'**
  String get filesGitXShowWhitespaceTooltip;

  /// No description provided for @filesGitXStatusNotLoaded.
  ///
  /// In en, this message translates to:
  /// **'Git status not loaded on this device.'**
  String get filesGitXStatusNotLoaded;

  /// No description provided for @filesGitXWordWrapTooltip.
  ///
  /// In en, this message translates to:
  /// **'Word Wrap'**
  String get filesGitXWordWrapTooltip;

  /// No description provided for @filesGitXWorkingTreeClean.
  ///
  /// In en, this message translates to:
  /// **'Working tree clean'**
  String get filesGitXWorkingTreeClean;

  /// No description provided for @filesScreenTabChanges.
  ///
  /// In en, this message translates to:
  /// **'Changes'**
  String get filesScreenTabChanges;

  /// No description provided for @filesScreenTabFiles.
  ///
  /// In en, this message translates to:
  /// **'Files'**
  String get filesScreenTabFiles;

  /// No description provided for @filesXErrDefault.
  ///
  /// In en, this message translates to:
  /// **'Couldn’t list this directory ({code}).'**
  String filesXErrDefault(Object code);

  /// No description provided for @filesXErrNoHandler.
  ///
  /// In en, this message translates to:
  /// **'Update the daemon on this machine — older version doesn’t support file listing.'**
  String get filesXErrNoHandler;

  /// No description provided for @filesXErrNotADirectory.
  ///
  /// In en, this message translates to:
  /// **'Project path is not a directory.'**
  String get filesXErrNotADirectory;

  /// No description provided for @filesXErrOutsideProject.
  ///
  /// In en, this message translates to:
  /// **'Path is outside the project root.'**
  String get filesXErrOutsideProject;

  /// No description provided for @filesXErrPathNotFound.
  ///
  /// In en, this message translates to:
  /// **'The project directory was not found on the machine.'**
  String get filesXErrPathNotFound;

  /// No description provided for @filesXErrPermissionDenied.
  ///
  /// In en, this message translates to:
  /// **'Permission denied reading this directory.'**
  String get filesXErrPermissionDenied;

  /// No description provided for @filesXErrTimeout.
  ///
  /// In en, this message translates to:
  /// **'The machine took too long to respond.'**
  String get filesXErrTimeout;

  /// No description provided for @filesXMachineOffline.
  ///
  /// In en, this message translates to:
  /// **'Machine offline, {detail}.'**
  String filesXMachineOffline(Object detail);

  /// No description provided for @filesXNoFiles.
  ///
  /// In en, this message translates to:
  /// **'No files'**
  String get filesXNoFiles;

  /// No description provided for @filesXNotLoaded.
  ///
  /// In en, this message translates to:
  /// **'Files not loaded on this device.'**
  String get filesXNotLoaded;

  /// No description provided for @filesXOfflineDetailDefault.
  ///
  /// In en, this message translates to:
  /// **'files could be outdated'**
  String get filesXOfflineDetailDefault;

  /// No description provided for @filesXProjectLabel.
  ///
  /// In en, this message translates to:
  /// **'project: {cwd}'**
  String filesXProjectLabel(Object cwd);

  /// No description provided for @filesXReconnectToBrowse.
  ///
  /// In en, this message translates to:
  /// **'Reconnect the machine to browse them.'**
  String get filesXReconnectToBrowse;

  /// No description provided for @filterAgentType.
  ///
  /// In en, this message translates to:
  /// **'Agent Type'**
  String get filterAgentType;

  /// No description provided for @filterAgentTypeHeader.
  ///
  /// In en, this message translates to:
  /// **'AGENT TYPE'**
  String get filterAgentTypeHeader;

  /// No description provided for @filterAll.
  ///
  /// In en, this message translates to:
  /// **'All'**
  String get filterAll;

  /// No description provided for @filterAllTime.
  ///
  /// In en, this message translates to:
  /// **'All Time'**
  String get filterAllTime;

  /// No description provided for @filterClosed.
  ///
  /// In en, this message translates to:
  /// **'Archived'**
  String get filterClosed;

  /// No description provided for @filterCustomRange.
  ///
  /// In en, this message translates to:
  /// **'Custom Range'**
  String get filterCustomRange;

  /// No description provided for @filterDate.
  ///
  /// In en, this message translates to:
  /// **'Date'**
  String get filterDate;

  /// No description provided for @filterDateRange.
  ///
  /// In en, this message translates to:
  /// **'Date Range'**
  String get filterDateRange;

  /// No description provided for @filterDateRangeHeader.
  ///
  /// In en, this message translates to:
  /// **'DATE RANGE'**
  String get filterDateRangeHeader;

  /// No description provided for @filterFilter.
  ///
  /// In en, this message translates to:
  /// **'Filter'**
  String get filterFilter;

  /// No description provided for @filterGroupBy.
  ///
  /// In en, this message translates to:
  /// **'Group By'**
  String get filterGroupBy;

  /// No description provided for @filterInProgress.
  ///
  /// In en, this message translates to:
  /// **'In progress'**
  String get filterInProgress;

  /// No description provided for @filterInReview.
  ///
  /// In en, this message translates to:
  /// **'In review'**
  String get filterInReview;

  /// No description provided for @filterLast7Days.
  ///
  /// In en, this message translates to:
  /// **'Last 7 Days'**
  String get filterLast7Days;

  /// No description provided for @filterNotClosed.
  ///
  /// In en, this message translates to:
  /// **'Active'**
  String get filterNotClosed;

  /// No description provided for @filterProject.
  ///
  /// In en, this message translates to:
  /// **'Project'**
  String get filterProject;

  /// No description provided for @filterStatus.
  ///
  /// In en, this message translates to:
  /// **'Status'**
  String get filterStatus;

  /// No description provided for @filterStatusHeader.
  ///
  /// In en, this message translates to:
  /// **'STATUS'**
  String get filterStatusHeader;

  /// No description provided for @filterTime.
  ///
  /// In en, this message translates to:
  /// **'Time'**
  String get filterTime;

  /// No description provided for @filterType.
  ///
  /// In en, this message translates to:
  /// **'Type'**
  String get filterType;

  /// No description provided for @giftDialogFreeCredits.
  ///
  /// In en, this message translates to:
  /// **'Yay! You got 5 free credits!'**
  String get giftDialogFreeCredits;

  /// No description provided for @helpFeedbackBlog.
  ///
  /// In en, this message translates to:
  /// **'Blog'**
  String get helpFeedbackBlog;

  /// No description provided for @helpFeedbackChangelog.
  ///
  /// In en, this message translates to:
  /// **'Changelog'**
  String get helpFeedbackChangelog;

  /// No description provided for @helpFeedbackContactUs.
  ///
  /// In en, this message translates to:
  /// **'Contact Us'**
  String get helpFeedbackContactUs;

  /// No description provided for @helpFeedbackDocumentation.
  ///
  /// In en, this message translates to:
  /// **'Documentation'**
  String get helpFeedbackDocumentation;

  /// No description provided for @helpFeedbackFeatureRequest.
  ///
  /// In en, this message translates to:
  /// **'Feature Request & Bug Reports'**
  String get helpFeedbackFeatureRequest;

  /// No description provided for @helpFeedbackFeedback.
  ///
  /// In en, this message translates to:
  /// **'Feedback'**
  String get helpFeedbackFeedback;

  /// No description provided for @helpFeedbackTitle.
  ///
  /// In en, this message translates to:
  /// **'Help & Feedback'**
  String get helpFeedbackTitle;

  /// No description provided for @homeCloseFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to archive session. Please try again.'**
  String get homeCloseFailed;

  /// No description provided for @homeDeleteFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to delete session. Please try again.'**
  String get homeDeleteFailed;

  /// No description provided for @homeErrorConnecting.
  ///
  /// In en, this message translates to:
  /// **'Connecting to the server. If this persists, sign in again from Account Page.'**
  String get homeErrorConnecting;

  /// No description provided for @homeErrorLoadSessionsFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to load sessions. Please try again.'**
  String get homeErrorLoadSessionsFailed;

  /// No description provided for @homeErrorOffline.
  ///
  /// In en, this message translates to:
  /// **'No internet connection. Please check your connection.'**
  String get homeErrorOffline;

  /// No description provided for @homeErrorOfflineCached.
  ///
  /// In en, this message translates to:
  /// **'No internet connection. Showing cached data.'**
  String get homeErrorOfflineCached;

  /// No description provided for @homeErrorServiceUnavailable.
  ///
  /// In en, this message translates to:
  /// **'Unable to reach the service right now.'**
  String get homeErrorServiceUnavailable;

  /// No description provided for @homeErrorServiceUnavailableRetry.
  ///
  /// In en, this message translates to:
  /// **'Unable to reach the service right now. Please try again shortly.'**
  String get homeErrorServiceUnavailableRetry;

  /// No description provided for @homeErrorSessionExpired.
  ///
  /// In en, this message translates to:
  /// **'Your session has expired. Please sign in again to continue.'**
  String get homeErrorSessionExpired;

  /// No description provided for @homeGroupNoProject.
  ///
  /// In en, this message translates to:
  /// **'No Project'**
  String get homeGroupNoProject;

  /// No description provided for @homeGroupPinned.
  ///
  /// In en, this message translates to:
  /// **'Pinned'**
  String get homeGroupPinned;

  /// No description provided for @homePinFailed.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t pin session'**
  String get homePinFailed;

  /// No description provided for @homeRenameFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to rename session. Please try again.'**
  String get homeRenameFailed;

  /// No description provided for @homeSessionClosed.
  ///
  /// In en, this message translates to:
  /// **'Session archived'**
  String get homeSessionClosed;

  /// No description provided for @homeSessionDeleted.
  ///
  /// In en, this message translates to:
  /// **'Session deleted successfully'**
  String get homeSessionDeleted;

  /// No description provided for @homeSessionRenamed.
  ///
  /// In en, this message translates to:
  /// **'Session renamed successfully'**
  String get homeSessionRenamed;

  /// No description provided for @homeUnpinFailed.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t unpin session'**
  String get homeUnpinFailed;

  /// No description provided for @impactHeadline.
  ///
  /// In en, this message translates to:
  /// **'{phrase} with AI coding agents anywhere you go'**
  String impactHeadline(Object phrase);

  /// No description provided for @impactWithRatingHeadline.
  ///
  /// In en, this message translates to:
  /// **'Build faster with AI coding agents anywhere you go'**
  String get impactWithRatingHeadline;

  /// No description provided for @impactWithRatingNameMarcus.
  ///
  /// In en, this message translates to:
  /// **'Marcus'**
  String get impactWithRatingNameMarcus;

  /// No description provided for @impactWithRatingNameSarah.
  ///
  /// In en, this message translates to:
  /// **'Sarah'**
  String get impactWithRatingNameSarah;

  /// No description provided for @impactWithRatingNameTom.
  ///
  /// In en, this message translates to:
  /// **'Tom'**
  String get impactWithRatingNameTom;

  /// No description provided for @impactWithRatingTestimonialMarcus.
  ///
  /// In en, this message translates to:
  /// **'Vicoa changed how I work. I never miss opportunities to ship with all the coding agents in my phone.'**
  String get impactWithRatingTestimonialMarcus;

  /// No description provided for @impactWithRatingTestimonialSarah.
  ///
  /// In en, this message translates to:
  /// **'Finally! Claude Code on mobile. I can code during my commute and fix bugs on the go.'**
  String get impactWithRatingTestimonialSarah;

  /// No description provided for @impactWithRatingTestimonialTom.
  ///
  /// In en, this message translates to:
  /// **'Perfect for developers on the move. Debug, refactor, and build new features from my phone. Amazing!'**
  String get impactWithRatingTestimonialTom;

  /// No description provided for @infoDialogAreYouSure.
  ///
  /// In en, this message translates to:
  /// **'Are you sure?'**
  String get infoDialogAreYouSure;

  /// No description provided for @introLandingPage1Item1.
  ///
  /// In en, this message translates to:
  /// **'Send commands from anywhere'**
  String get introLandingPage1Item1;

  /// No description provided for @introLandingPage1Item2.
  ///
  /// In en, this message translates to:
  /// **'Get instant AI responses'**
  String get introLandingPage1Item2;

  /// No description provided for @introLandingPage1Item3.
  ///
  /// In en, this message translates to:
  /// **'Sync across all devices'**
  String get introLandingPage1Item3;

  /// No description provided for @introLandingPage1Subtitle.
  ///
  /// In en, this message translates to:
  /// **'Send commands to AI agent running on your computer, right from your phone.'**
  String get introLandingPage1Subtitle;

  /// No description provided for @introLandingPage1Title.
  ///
  /// In en, this message translates to:
  /// **'Remote AI Coding\nfrom your Phone'**
  String get introLandingPage1Title;

  /// No description provided for @introLandingPage2Item1.
  ///
  /// In en, this message translates to:
  /// **'Instant alerts when tasks done'**
  String get introLandingPage2Item1;

  /// No description provided for @introLandingPage2Item2.
  ///
  /// In en, this message translates to:
  /// **'One-tap approvals from your phone'**
  String get introLandingPage2Item2;

  /// No description provided for @introLandingPage2Item3.
  ///
  /// In en, this message translates to:
  /// **'Chat with your agents on the go'**
  String get introLandingPage2Item3;

  /// No description provided for @introLandingPage2Subtitle.
  ///
  /// In en, this message translates to:
  /// **'Get instant alerts when your agent needs input and keep building without touching your laptop.'**
  String get introLandingPage2Subtitle;

  /// No description provided for @introLandingPage2Title.
  ///
  /// In en, this message translates to:
  /// **'Your Agent Works.\nYou Stay Notified.'**
  String get introLandingPage2Title;

  /// No description provided for @introLandingPage3Item1.
  ///
  /// In en, this message translates to:
  /// **'Works with Claude Code, Codex, and OpenCode'**
  String get introLandingPage3Item1;

  /// No description provided for @introLandingPage3Item2.
  ///
  /// In en, this message translates to:
  /// **'All your agent sessions in one place'**
  String get introLandingPage3Item2;

  /// No description provided for @introLandingPage3Item3.
  ///
  /// In en, this message translates to:
  /// **'Browse past conversations'**
  String get introLandingPage3Item3;

  /// No description provided for @introLandingPage3Subtitle.
  ///
  /// In en, this message translates to:
  /// **'Monitor all your agents across projects, browse history, and more-all in one place.'**
  String get introLandingPage3Subtitle;

  /// No description provided for @introLandingPage3Title.
  ///
  /// In en, this message translates to:
  /// **'One Interface for\nAll Your Agents'**
  String get introLandingPage3Title;

  /// No description provided for @introLandingPage4Item1.
  ///
  /// In en, this message translates to:
  /// **'Download the desktop app'**
  String get introLandingPage4Item1;

  /// No description provided for @introLandingPage4Item2.
  ///
  /// In en, this message translates to:
  /// **'Sign in with the same account'**
  String get introLandingPage4Item2;

  /// No description provided for @introLandingPage4Item3.
  ///
  /// In en, this message translates to:
  /// **'Paired instantly! Start coding.'**
  String get introLandingPage4Item3;

  /// No description provided for @introLandingPage4Subtitle.
  ///
  /// In en, this message translates to:
  /// **'A few clicks and you\'re ready to manage desktop projects right from your phone.'**
  String get introLandingPage4Subtitle;

  /// No description provided for @introLandingPage4Title.
  ///
  /// In en, this message translates to:
  /// **'Connect in Seconds'**
  String get introLandingPage4Title;

  /// No description provided for @landingHeadline.
  ///
  /// In en, this message translates to:
  /// **'Remote AI coding\nfrom your phone'**
  String get landingHeadline;

  /// No description provided for @landingSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Run dozens of coding agents anywhere'**
  String get landingSubtitle;

  /// No description provided for @landingSupports.
  ///
  /// In en, this message translates to:
  /// **'Supports'**
  String get landingSupports;

  /// No description provided for @languageAutomatic.
  ///
  /// In en, this message translates to:
  /// **'Automatic'**
  String get languageAutomatic;

  /// Autonym for the Simplified Chinese language (same in every locale)
  ///
  /// In en, this message translates to:
  /// **'中文'**
  String get languageChinese;

  /// Autonym for the English language (same in every locale)
  ///
  /// In en, this message translates to:
  /// **'English'**
  String get languageEnglish;

  /// Language option that follows the device locale
  ///
  /// In en, this message translates to:
  /// **'Follow system'**
  String get languageFollowSystem;

  /// No description provided for @machineActionsRemoveContent.
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to remove this machine? You won\'t be able to start new sessions from it until you run the Vicoa CLI again.'**
  String get machineActionsRemoveContent;

  /// No description provided for @machineActionsRemoveTitle.
  ///
  /// In en, this message translates to:
  /// **'Remove Machine'**
  String get machineActionsRemoveTitle;

  /// No description provided for @machineActionsRemoving.
  ///
  /// In en, this message translates to:
  /// **'Removing machine...'**
  String get machineActionsRemoving;

  /// No description provided for @machineActionsRenamePlaceholder.
  ///
  /// In en, this message translates to:
  /// **'Enter machine name...'**
  String get machineActionsRenamePlaceholder;

  /// No description provided for @machineActionsRenameTitle.
  ///
  /// In en, this message translates to:
  /// **'Rename Machine'**
  String get machineActionsRenameTitle;

  /// No description provided for @machineActionsRenaming.
  ///
  /// In en, this message translates to:
  /// **'Renaming machine...'**
  String get machineActionsRenaming;

  /// No description provided for @machineDetailAgentNotFound.
  ///
  /// In en, this message translates to:
  /// **'Not found'**
  String get machineDetailAgentNotFound;

  /// No description provided for @machineDetailAgents.
  ///
  /// In en, this message translates to:
  /// **'Agents'**
  String get machineDetailAgents;

  /// No description provided for @machineDetailCautionZone.
  ///
  /// In en, this message translates to:
  /// **'Caution Zone'**
  String get machineDetailCautionZone;

  /// No description provided for @machineDetailCouldNotLoad.
  ///
  /// In en, this message translates to:
  /// **'Could not load machine'**
  String get machineDetailCouldNotLoad;

  /// No description provided for @machineDetailHomeDirectory.
  ///
  /// In en, this message translates to:
  /// **'Home directory'**
  String get machineDetailHomeDirectory;

  /// No description provided for @machineDetailHostname.
  ///
  /// In en, this message translates to:
  /// **'Hostname'**
  String get machineDetailHostname;

  /// No description provided for @machineDetailInstalled.
  ///
  /// In en, this message translates to:
  /// **'Installed'**
  String get machineDetailInstalled;

  /// No description provided for @machineDetailLastHeartbeat.
  ///
  /// In en, this message translates to:
  /// **'Last heartbeat'**
  String get machineDetailLastHeartbeat;

  /// No description provided for @machineDetailMachine.
  ///
  /// In en, this message translates to:
  /// **'Machine'**
  String get machineDetailMachine;

  /// No description provided for @machineDetailNotFound.
  ///
  /// In en, this message translates to:
  /// **'Machine not found'**
  String get machineDetailNotFound;

  /// No description provided for @machineDetailOffline.
  ///
  /// In en, this message translates to:
  /// **'Offline'**
  String get machineDetailOffline;

  /// No description provided for @machineDetailOnline.
  ///
  /// In en, this message translates to:
  /// **'Online'**
  String get machineDetailOnline;

  /// No description provided for @machineDetailPlatform.
  ///
  /// In en, this message translates to:
  /// **'Platform'**
  String get machineDetailPlatform;

  /// No description provided for @machineDetailRemoveDescription.
  ///
  /// In en, this message translates to:
  /// **'Remove this machine from your account. Session history will be preserved, but you will not be able to start new sessions on this machine.'**
  String get machineDetailRemoveDescription;

  /// No description provided for @machineDetailRemoveMachine.
  ///
  /// In en, this message translates to:
  /// **'Remove machine'**
  String get machineDetailRemoveMachine;

  /// No description provided for @machineDetailRunPrefix.
  ///
  /// In en, this message translates to:
  /// **'Run '**
  String get machineDetailRunPrefix;

  /// No description provided for @machineDetailRunSuffix.
  ///
  /// In en, this message translates to:
  /// **' to bring it online'**
  String get machineDetailRunSuffix;

  /// No description provided for @machineDetailStatus.
  ///
  /// In en, this message translates to:
  /// **'Status'**
  String get machineDetailStatus;

  /// No description provided for @machineDetailSystem.
  ///
  /// In en, this message translates to:
  /// **'System'**
  String get machineDetailSystem;

  /// No description provided for @machineDetailUnknown.
  ///
  /// In en, this message translates to:
  /// **'Unknown'**
  String get machineDetailUnknown;

  /// No description provided for @machineDetailVicoaCli.
  ///
  /// In en, this message translates to:
  /// **'Vicoa CLI'**
  String get machineDetailVicoaCli;

  /// No description provided for @machinesCouldNotLoad.
  ///
  /// In en, this message translates to:
  /// **'Could not load machines'**
  String get machinesCouldNotLoad;

  /// No description provided for @machinesMachineRemoved.
  ///
  /// In en, this message translates to:
  /// **'Machine removed'**
  String get machinesMachineRemoved;

  /// No description provided for @machinesNoMachinesSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Run the Vicoa CLI on a computer to connect it, then start remote sessions from anywhere.'**
  String get machinesNoMachinesSubtitle;

  /// No description provided for @machinesNoMachinesYet.
  ///
  /// In en, this message translates to:
  /// **'No machines yet'**
  String get machinesNoMachinesYet;

  /// No description provided for @machinesPullToRefresh.
  ///
  /// In en, this message translates to:
  /// **'Pull to refresh to try again.'**
  String get machinesPullToRefresh;

  /// No description provided for @machinesTitle.
  ///
  /// In en, this message translates to:
  /// **'Machines'**
  String get machinesTitle;

  /// No description provided for @markdownXMoreLines.
  ///
  /// In en, this message translates to:
  /// **'{count} more lines'**
  String markdownXMoreLines(Object count);

  /// No description provided for @messageSelectionSheetCount.
  ///
  /// In en, this message translates to:
  /// **'{selected} of {total} selected'**
  String messageSelectionSheetCount(Object selected, Object total);

  /// No description provided for @messageSelectionSheetDeselectAll.
  ///
  /// In en, this message translates to:
  /// **'Deselect All'**
  String get messageSelectionSheetDeselectAll;

  /// No description provided for @messageSelectionSheetSelectAll.
  ///
  /// In en, this message translates to:
  /// **'Select All'**
  String get messageSelectionSheetSelectAll;

  /// No description provided for @messageSelectionSheetTitle.
  ///
  /// In en, this message translates to:
  /// **'Select Messages'**
  String get messageSelectionSheetTitle;

  /// No description provided for @messageSelectionSheetYou.
  ///
  /// In en, this message translates to:
  /// **'You'**
  String get messageSelectionSheetYou;

  /// No description provided for @newSessionAddToChat.
  ///
  /// In en, this message translates to:
  /// **'Add to chat'**
  String get newSessionAddToChat;

  /// No description provided for @newSessionAgent.
  ///
  /// In en, this message translates to:
  /// **'Agent'**
  String get newSessionAgent;

  /// No description provided for @newSessionAgentDidNotStart.
  ///
  /// In en, this message translates to:
  /// **'{label} didn\'t start on this machine.\n\nMake sure it\'s installed there and your Vicoa daemon is up to date, then try again.'**
  String newSessionAgentDidNotStart(Object label);

  /// No description provided for @newSessionCurrentBranch.
  ///
  /// In en, this message translates to:
  /// **'Current branch'**
  String get newSessionCurrentBranch;

  /// No description provided for @newSessionLoadingMachines.
  ///
  /// In en, this message translates to:
  /// **'Loading machines...'**
  String get newSessionLoadingMachines;

  /// No description provided for @newSessionMachine.
  ///
  /// In en, this message translates to:
  /// **'Machine'**
  String get newSessionMachine;

  /// No description provided for @newSessionNewSession.
  ///
  /// In en, this message translates to:
  /// **'New Session'**
  String get newSessionNewSession;

  /// No description provided for @newSessionNewWorktree.
  ///
  /// In en, this message translates to:
  /// **'New worktree'**
  String get newSessionNewWorktree;

  /// No description provided for @newSessionOffline.
  ///
  /// In en, this message translates to:
  /// **'(offline)'**
  String get newSessionOffline;

  /// No description provided for @newSessionRunPrefix.
  ///
  /// In en, this message translates to:
  /// **'Run '**
  String get newSessionRunPrefix;

  /// No description provided for @newSessionSelectMachine.
  ///
  /// In en, this message translates to:
  /// **'Select a machine'**
  String get newSessionSelectMachine;

  /// No description provided for @newSessionStartedNoStatus.
  ///
  /// In en, this message translates to:
  /// **'Session started but could not determine status.'**
  String get newSessionStartedNoStatus;

  /// No description provided for @newSessionTheAgent.
  ///
  /// In en, this message translates to:
  /// **'The agent'**
  String get newSessionTheAgent;

  /// No description provided for @newSessionToBringOnline.
  ///
  /// In en, this message translates to:
  /// **' to bring your machine online.'**
  String get newSessionToBringOnline;

  /// No description provided for @newSessionUnableToStart.
  ///
  /// In en, this message translates to:
  /// **'Unable to Start Session'**
  String get newSessionUnableToStart;

  /// No description provided for @newSessionUnableToStartBody.
  ///
  /// In en, this message translates to:
  /// **'This could be due to:\n\n• The machine is not responding\n• Network connection issues\n• The directory path is invalid\n\nPlease check machine status and try again.'**
  String get newSessionUnableToStartBody;

  /// No description provided for @newSessionWorkingDirectory.
  ///
  /// In en, this message translates to:
  /// **'Working Directory'**
  String get newSessionWorkingDirectory;

  /// No description provided for @newSessionWorktree.
  ///
  /// In en, this message translates to:
  /// **'Worktree'**
  String get newSessionWorktree;

  /// No description provided for @newsAndConnector.
  ///
  /// In en, this message translates to:
  /// **' and '**
  String get newsAndConnector;

  /// No description provided for @newsBadNewsPrefix.
  ///
  /// In en, this message translates to:
  /// **'The bad news is that\n'**
  String get newsBadNewsPrefix;

  /// No description provided for @newsCodeFromPhone.
  ///
  /// In en, this message translates to:
  /// **'code from your phone.'**
  String get newsCodeFromPhone;

  /// No description provided for @newsCodingNext12Months.
  ///
  /// In en, this message translates to:
  /// **'\ncoding in the next 12 months.'**
  String get newsCodingNext12Months;

  /// No description provided for @newsGetNotified.
  ///
  /// In en, this message translates to:
  /// **'get notified'**
  String get newsGetNotified;

  /// No description provided for @newsGreatNewsPrefix.
  ///
  /// In en, this message translates to:
  /// **'The great news is that \n'**
  String get newsGreatNewsPrefix;

  /// No description provided for @newsJustWaiting.
  ///
  /// In en, this message translates to:
  /// **'just waiting for the results'**
  String get newsJustWaiting;

  /// No description provided for @newsMinutesUnit.
  ///
  /// In en, this message translates to:
  /// **' minutes '**
  String get newsMinutesUnit;

  /// No description provided for @newsTransitHeadline.
  ///
  /// In en, this message translates to:
  /// **'Some not-so-good news  \nand some great news'**
  String get newsTransitHeadline;

  /// No description provided for @newsVicoaFreesYouUp.
  ///
  /// In en, this message translates to:
  /// **'Vicoa frees you up, you can '**
  String get newsVicoaFreesYouUp;

  /// No description provided for @newsWastedMinutes.
  ///
  /// In en, this message translates to:
  /// **'{minutes}+ minutes '**
  String newsWastedMinutes(Object minutes);

  /// No description provided for @newsYouWillSpend.
  ///
  /// In en, this message translates to:
  /// **'You will spend '**
  String get newsYouWillSpend;

  /// No description provided for @newsYouWillWaste.
  ///
  /// In en, this message translates to:
  /// **'You will waste '**
  String get newsYouWillWaste;

  /// No description provided for @noCreditSheetGetMoreFreeMessages.
  ///
  /// In en, this message translates to:
  /// **'Get More Free Messages'**
  String get noCreditSheetGetMoreFreeMessages;

  /// No description provided for @noCreditSheetGetMoreOrUnlock.
  ///
  /// In en, this message translates to:
  /// **'Get more free messages or unlock unlimited access with Vicoa Pro.'**
  String get noCreditSheetGetMoreOrUnlock;

  /// No description provided for @noCreditSheetInsufficientCredits.
  ///
  /// In en, this message translates to:
  /// **'Insufficient Credits'**
  String get noCreditSheetInsufficientCredits;

  /// No description provided for @noCreditSheetUpgradeToPro.
  ///
  /// In en, this message translates to:
  /// **'Upgrade to Vicoa Pro'**
  String get noCreditSheetUpgradeToPro;

  /// No description provided for @noCreditSheetUsedAllMessages.
  ///
  /// In en, this message translates to:
  /// **'You\'ve used all free messages.'**
  String get noCreditSheetUsedAllMessages;

  /// No description provided for @notificationAllSet.
  ///
  /// In en, this message translates to:
  /// **'You are all set!'**
  String get notificationAllSet;

  /// No description provided for @notificationDontMissOut.
  ///
  /// In en, this message translates to:
  /// **'Don\'t miss out notifications when your coding agent needs your input.\n'**
  String get notificationDontMissOut;

  /// No description provided for @notificationEnableButton.
  ///
  /// In en, this message translates to:
  /// **'Enable Notification'**
  String get notificationEnableButton;

  /// No description provided for @notificationInOnboardBody.
  ///
  /// In en, this message translates to:
  /// **'Don\'t miss out notifications when your coding agent needs your input.\n'**
  String get notificationInOnboardBody;

  /// No description provided for @notificationInOnboardEnable.
  ///
  /// In en, this message translates to:
  /// **'Enable Notifications'**
  String get notificationInOnboardEnable;

  /// No description provided for @notificationInOnboardMaybeLater.
  ///
  /// In en, this message translates to:
  /// **'Maybe later'**
  String get notificationInOnboardMaybeLater;

  /// No description provided for @notificationInOnboardTitle.
  ///
  /// In en, this message translates to:
  /// **'Turn on Notifications?'**
  String get notificationInOnboardTitle;

  /// No description provided for @notificationTitle.
  ///
  /// In en, this message translates to:
  /// **'Notifications'**
  String get notificationTitle;

  /// No description provided for @notificationTurnOnPrompt.
  ///
  /// In en, this message translates to:
  /// **'Turn on Notification?'**
  String get notificationTurnOnPrompt;

  /// No description provided for @onboardGetNotifiedInstantly.
  ///
  /// In en, this message translates to:
  /// **'Get notified instantly.'**
  String get onboardGetNotifiedInstantly;

  /// No description provided for @onboardGetStarted.
  ///
  /// In en, this message translates to:
  /// **'Get Started'**
  String get onboardGetStarted;

  /// No description provided for @onboardNoMoreIdleWaiting.
  ///
  /// In en, this message translates to:
  /// **'No more idle waiting.'**
  String get onboardNoMoreIdleWaiting;

  /// No description provided for @onboardPickUpWhereLeftOff.
  ///
  /// In en, this message translates to:
  /// **'Pick up where you left off.'**
  String get onboardPickUpWhereLeftOff;

  /// No description provided for @onboardSlide1Body.
  ///
  /// In en, this message translates to:
  /// **'Start a task, let Claude Code, Codex, or OpenCode keep working while you focus elsewhere.'**
  String get onboardSlide1Body;

  /// No description provided for @onboardSlide2Body.
  ///
  /// In en, this message translates to:
  /// **'Take AI coding agents anywhere, continue your coding on your phone.'**
  String get onboardSlide2Body;

  /// No description provided for @onboardSlide3Body.
  ///
  /// In en, this message translates to:
  /// **'Get a ping when AI coding agents needs input, continue coding with a tap.'**
  String get onboardSlide3Body;

  /// No description provided for @personalizingConfiguringBest.
  ///
  /// In en, this message translates to:
  /// **'Configuring the best set up for you'**
  String get personalizingConfiguringBest;

  /// No description provided for @personalizingHeadline.
  ///
  /// In en, this message translates to:
  /// **'Your AI Agents\nare almost ready'**
  String get personalizingHeadline;

  /// No description provided for @personalizingSettingUp.
  ///
  /// In en, this message translates to:
  /// **'Setting Up'**
  String get personalizingSettingUp;

  /// No description provided for @personalizingSocialProof.
  ///
  /// In en, this message translates to:
  /// **'People who use Vicoa get more done\nwith coding agents.'**
  String get personalizingSocialProof;

  /// No description provided for @proBenefitsPrioritySupportDesc.
  ///
  /// In en, this message translates to:
  /// **'Get faster response times and priority support when you need help.'**
  String get proBenefitsPrioritySupportDesc;

  /// No description provided for @proBenefitsPrioritySupportTitle.
  ///
  /// In en, this message translates to:
  /// **'Priority Support'**
  String get proBenefitsPrioritySupportTitle;

  /// No description provided for @proBenefitsSubtitle.
  ///
  /// In en, this message translates to:
  /// **'You\'re enjoying all the premium features:'**
  String get proBenefitsSubtitle;

  /// No description provided for @proBenefitsSyncDesc.
  ///
  /// In en, this message translates to:
  /// **'Seamlessly sync your conversations and data across all your devices.'**
  String get proBenefitsSyncDesc;

  /// No description provided for @proBenefitsSyncTitle.
  ///
  /// In en, this message translates to:
  /// **'Unlimited Cross-Device Sync'**
  String get proBenefitsSyncTitle;

  /// No description provided for @proBenefitsTitle.
  ///
  /// In en, this message translates to:
  /// **'Vicoa Pro Benefits'**
  String get proBenefitsTitle;

  /// No description provided for @proBenefitsUnlimitedMessagesDesc.
  ///
  /// In en, this message translates to:
  /// **'Send unlimited messages to AI coding agents anywhere without any limits.'**
  String get proBenefitsUnlimitedMessagesDesc;

  /// No description provided for @proBenefitsUnlimitedMessagesTitle.
  ///
  /// In en, this message translates to:
  /// **'Unlimited Messages'**
  String get proBenefitsUnlimitedMessagesTitle;

  /// No description provided for @proBenefitsVoiceInputDesc.
  ///
  /// In en, this message translates to:
  /// **'Talk to your AI coding agents hands-free.'**
  String get proBenefitsVoiceInputDesc;

  /// No description provided for @proBenefitsVoiceInputTitle.
  ///
  /// In en, this message translates to:
  /// **'Voice Input'**
  String get proBenefitsVoiceInputTitle;

  /// No description provided for @profileAccount.
  ///
  /// In en, this message translates to:
  /// **'Account'**
  String get profileAccount;

  /// No description provided for @profileAppearance.
  ///
  /// In en, this message translates to:
  /// **'Appearance'**
  String get profileAppearance;

  /// No description provided for @profileFreeMessages.
  ///
  /// In en, this message translates to:
  /// **'Free Messages'**
  String get profileFreeMessages;

  /// No description provided for @profileHelpFeedback.
  ///
  /// In en, this message translates to:
  /// **'Help & Feedback'**
  String get profileHelpFeedback;

  /// No description provided for @profileInviteFriends.
  ///
  /// In en, this message translates to:
  /// **'Invite Friends & Get Rewards'**
  String get profileInviteFriends;

  /// No description provided for @profileJoinDiscord.
  ///
  /// In en, this message translates to:
  /// **'Join Discord'**
  String get profileJoinDiscord;

  /// No description provided for @profileJoinPro.
  ///
  /// In en, this message translates to:
  /// **'Join Vicoa Pro'**
  String get profileJoinPro;

  /// No description provided for @profileMachines.
  ///
  /// In en, this message translates to:
  /// **'Machines'**
  String get profileMachines;

  /// No description provided for @profileNotifications.
  ///
  /// In en, this message translates to:
  /// **'Notifications'**
  String get profileNotifications;

  /// No description provided for @profileProMember.
  ///
  /// In en, this message translates to:
  /// **'Vicoa Pro Member'**
  String get profileProMember;

  /// No description provided for @profileProSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Unlimited Agents and Messages'**
  String get profileProSubtitle;

  /// No description provided for @profileReportIssue.
  ///
  /// In en, this message translates to:
  /// **'Report an Issue'**
  String get profileReportIssue;

  /// No description provided for @profileSubscription.
  ///
  /// In en, this message translates to:
  /// **'Subscription'**
  String get profileSubscription;

  /// No description provided for @profileTitle.
  ///
  /// In en, this message translates to:
  /// **'Profile'**
  String get profileTitle;

  /// No description provided for @profileTutorials.
  ///
  /// In en, this message translates to:
  /// **'Tutorials'**
  String get profileTutorials;

  /// No description provided for @profileVoiceAssistance.
  ///
  /// In en, this message translates to:
  /// **'Voice Assistance'**
  String get profileVoiceAssistance;

  /// No description provided for @ratingDevelopersLike.
  ///
  /// In en, this message translates to:
  /// **'+100 developers like Vicoa'**
  String get ratingDevelopersLike;

  /// No description provided for @ratingLetsGetStarted.
  ///
  /// In en, this message translates to:
  /// **'Let\'s get started'**
  String get ratingLetsGetStarted;

  /// No description provided for @ratingMadeForYou.
  ///
  /// In en, this message translates to:
  /// **'Vicoa was made for \npeople like you'**
  String get ratingMadeForYou;

  /// No description provided for @ratingTestimonialMarcus.
  ///
  /// In en, this message translates to:
  /// **'Vicoa changed how I work. Having OpenCode anywhere means I never miss opportunities to ship.'**
  String get ratingTestimonialMarcus;

  /// No description provided for @ratingTestimonialSarah.
  ///
  /// In en, this message translates to:
  /// **'Finally! Claude Code on mobile. I can code during my commute and fix bugs on the go.'**
  String get ratingTestimonialSarah;

  /// No description provided for @ratingTestimonialTom.
  ///
  /// In en, this message translates to:
  /// **'Perfect for developers on the move. Debug, refactor, and build new features from my phone - amazing!'**
  String get ratingTestimonialTom;

  /// No description provided for @ratingTitle.
  ///
  /// In en, this message translates to:
  /// **'Give us a rating'**
  String get ratingTitle;

  /// No description provided for @realtimeStatusBannerReconnecting.
  ///
  /// In en, this message translates to:
  /// **'Reconnecting…'**
  String get realtimeStatusBannerReconnecting;

  /// No description provided for @referFriendsAdditionalRewards.
  ///
  /// In en, this message translates to:
  /// **'Additional Rewards'**
  String get referFriendsAdditionalRewards;

  /// No description provided for @referFriendsCodeUnavailableBody.
  ///
  /// In en, this message translates to:
  /// **'We\'re unable to generate your referral code at the moment. Please try again later or reach out for help.'**
  String get referFriendsCodeUnavailableBody;

  /// No description provided for @referFriendsCodeUnavailableTitle.
  ///
  /// In en, this message translates to:
  /// **'Referral Code Unavailable'**
  String get referFriendsCodeUnavailableTitle;

  /// No description provided for @referFriendsComeBackToClaim.
  ///
  /// In en, this message translates to:
  /// **'Come back to claim free messages after your friend uses your code.'**
  String get referFriendsComeBackToClaim;

  /// No description provided for @referFriendsContinueToUse.
  ///
  /// In en, this message translates to:
  /// **'Continue to Use'**
  String get referFriendsContinueToUse;

  /// No description provided for @referFriendsCopiedToClipboard.
  ///
  /// In en, this message translates to:
  /// **'Copied to clipboard'**
  String get referFriendsCopiedToClipboard;

  /// No description provided for @referFriendsEmailUs.
  ///
  /// In en, this message translates to:
  /// **'Email us'**
  String get referFriendsEmailUs;

  /// No description provided for @referFriendsGotRewardMessages.
  ///
  /// In en, this message translates to:
  /// **'Yay! You got {count} free messages for referring friends!'**
  String referFriendsGotRewardMessages(Object count);

  /// No description provided for @referFriendsGrabYourCode.
  ///
  /// In en, this message translates to:
  /// **'Grab Your Referral Code'**
  String get referFriendsGrabYourCode;

  /// No description provided for @referFriendsInvitedCount.
  ///
  /// In en, this message translates to:
  /// **'{count} invited'**
  String referFriendsInvitedCount(Object count);

  /// No description provided for @referFriendsOnlyRegisteredUsers.
  ///
  /// In en, this message translates to:
  /// **'Only registered users can invite friends.'**
  String get referFriendsOnlyRegisteredUsers;

  /// No description provided for @referFriendsShareMessage.
  ///
  /// In en, this message translates to:
  /// **'Hey, have you heard of Vicoa? With this app, I can run Claude Code, Codex, or OpenCode anywhere on my phone. You will get 50 free messages using my referral code: {code}. Download the app from https://apps.apple.com/app/id6751626168'**
  String referFriendsShareMessage(Object code);

  /// No description provided for @referFriendsShareSubject.
  ///
  /// In en, this message translates to:
  /// **'Vicoa: Code with AI Anytime, Anywhere'**
  String get referFriendsShareSubject;

  /// No description provided for @referFriendsShareYourCode.
  ///
  /// In en, this message translates to:
  /// **'Share your referral code'**
  String get referFriendsShareYourCode;

  /// No description provided for @referFriendsSignUpNow.
  ///
  /// In en, this message translates to:
  /// **'Sign Up Now'**
  String get referFriendsSignUpNow;

  /// No description provided for @referFriendsSignupReward.
  ///
  /// In en, this message translates to:
  /// **'✅ 50 free messages when they sign up with your referral code.'**
  String get referFriendsSignupReward;

  /// No description provided for @referFriendsTheyGet.
  ///
  /// In en, this message translates to:
  /// **'They get'**
  String get referFriendsTheyGet;

  /// No description provided for @referFriendsTierBenefit.
  ///
  /// In en, this message translates to:
  /// **'{count} friends → {reward} free messages'**
  String referFriendsTierBenefit(Object count, Object reward);

  /// No description provided for @referFriendsTitle.
  ///
  /// In en, this message translates to:
  /// **'Invite Friends & Get Rewards'**
  String get referFriendsTitle;

  /// No description provided for @referFriendsYouGet.
  ///
  /// In en, this message translates to:
  /// **'You get'**
  String get referFriendsYouGet;

  /// No description provided for @rpcErrorComputerOffline.
  ///
  /// In en, this message translates to:
  /// **'Your computer isn\'t connected right now. Make sure Vicoa is running on it, then try again.'**
  String get rpcErrorComputerOffline;

  /// No description provided for @rpcErrorTimeout.
  ///
  /// In en, this message translates to:
  /// **'Your computer took too long to respond. Check that Vicoa is running on it, then try again.'**
  String get rpcErrorTimeout;

  /// No description provided for @referralCodeHint.
  ///
  /// In en, this message translates to:
  /// **'Referral Code (Optional)'**
  String get referralCodeHint;

  /// No description provided for @referralCodeThisIsOptional.
  ///
  /// In en, this message translates to:
  /// **'This is optional'**
  String get referralCodeThisIsOptional;

  /// No description provided for @referralCodeTitle.
  ///
  /// In en, this message translates to:
  /// **'Do you have a \nReferral Code?'**
  String get referralCodeTitle;

  /// No description provided for @relativeTimeHours.
  ///
  /// In en, this message translates to:
  /// **'{count}h'**
  String relativeTimeHours(int count);

  /// No description provided for @relativeTimeMinutes.
  ///
  /// In en, this message translates to:
  /// **'{count}m'**
  String relativeTimeMinutes(int count);

  /// No description provided for @relativeTimeNow.
  ///
  /// In en, this message translates to:
  /// **'now'**
  String get relativeTimeNow;

  /// No description provided for @relativeTimeSeconds.
  ///
  /// In en, this message translates to:
  /// **'{count}s'**
  String relativeTimeSeconds(int count);

  /// No description provided for @renameDialogEnterSessionName.
  ///
  /// In en, this message translates to:
  /// **'Enter session name...'**
  String get renameDialogEnterSessionName;

  /// No description provided for @renameDialogRenameSession.
  ///
  /// In en, this message translates to:
  /// **'Rename Session'**
  String get renameDialogRenameSession;

  /// No description provided for @reportIssueDialogFailure.
  ///
  /// In en, this message translates to:
  /// **'Failed to send. Please try again.'**
  String get reportIssueDialogFailure;

  /// No description provided for @reportIssueDialogHint.
  ///
  /// In en, this message translates to:
  /// **'Describe the issue...'**
  String get reportIssueDialogHint;

  /// No description provided for @reportIssueDialogSending.
  ///
  /// In en, this message translates to:
  /// **'Sending...'**
  String get reportIssueDialogSending;

  /// No description provided for @reportIssueDialogSubmit.
  ///
  /// In en, this message translates to:
  /// **'Submit'**
  String get reportIssueDialogSubmit;

  /// No description provided for @reportIssueDialogSuccess.
  ///
  /// In en, this message translates to:
  /// **'Report sent. Thanks!'**
  String get reportIssueDialogSuccess;

  /// No description provided for @reviewDialogCharCount.
  ///
  /// In en, this message translates to:
  /// **'{current} / {max}'**
  String reviewDialogCharCount(Object current, Object max);

  /// No description provided for @reviewDialogCouldBeBetter.
  ///
  /// In en, this message translates to:
  /// **'🤔 Could be better'**
  String get reviewDialogCouldBeBetter;

  /// No description provided for @reviewDialogEnjoyingDescription.
  ///
  /// In en, this message translates to:
  /// **'We\'d love to know if you are enjoying Vicoa. Your feedback helps us improve!'**
  String get reviewDialogEnjoyingDescription;

  /// No description provided for @reviewDialogEnjoyingVicoa.
  ///
  /// In en, this message translates to:
  /// **'Enjoying Vicoa?'**
  String get reviewDialogEnjoyingVicoa;

  /// No description provided for @reviewDialogIssueHint.
  ///
  /// In en, this message translates to:
  /// **'The issue is…'**
  String get reviewDialogIssueHint;

  /// No description provided for @reviewDialogLoveIt.
  ///
  /// In en, this message translates to:
  /// **'😍 Love it!'**
  String get reviewDialogLoveIt;

  /// No description provided for @reviewDialogNeedsWorkDescription.
  ///
  /// In en, this message translates to:
  /// **'Something not quite right? Tell us, so we can make it work for you.'**
  String get reviewDialogNeedsWorkDescription;

  /// No description provided for @reviewDialogRateOnAppStore.
  ///
  /// In en, this message translates to:
  /// **'Rate on App Store'**
  String get reviewDialogRateOnAppStore;

  /// No description provided for @reviewDialogReviewDescription.
  ///
  /// In en, this message translates to:
  /// **'Your review helps spread the word and motivate us to make Vicoa even better!'**
  String get reviewDialogReviewDescription;

  /// No description provided for @reviewDialogReviewVicoa.
  ///
  /// In en, this message translates to:
  /// **'Review Vicoa :)'**
  String get reviewDialogReviewVicoa;

  /// No description provided for @reviewDialogSendFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to send. Please try again.'**
  String get reviewDialogSendFailed;

  /// No description provided for @reviewDialogSendFeedback.
  ///
  /// In en, this message translates to:
  /// **'Send Feedback'**
  String get reviewDialogSendFeedback;

  /// No description provided for @reviewDialogSending.
  ///
  /// In en, this message translates to:
  /// **'Sending…'**
  String get reviewDialogSending;

  /// No description provided for @reviewDialogThankYou.
  ///
  /// In en, this message translates to:
  /// **'Thank you for your feedback!'**
  String get reviewDialogThankYou;

  /// No description provided for @reviewDialogWhatCouldBeBetter.
  ///
  /// In en, this message translates to:
  /// **'What could be better?'**
  String get reviewDialogWhatCouldBeBetter;

  /// No description provided for @sessionActionsArchive.
  ///
  /// In en, this message translates to:
  /// **'Archive'**
  String get sessionActionsArchive;

  /// No description provided for @chatOptionsResume.
  ///
  /// In en, this message translates to:
  /// **'Resume'**
  String get chatOptionsResume;

  /// No description provided for @sessionResumeOffline.
  ///
  /// In en, this message translates to:
  /// **'Your computer is offline. Bring it back online to resume.'**
  String get sessionResumeOffline;

  /// No description provided for @sessionResumeFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to resume session'**
  String get sessionResumeFailed;

  /// No description provided for @sessionActionsCloseContent.
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to archive this session?'**
  String get sessionActionsCloseContent;

  /// No description provided for @sessionActionsCloseTitle.
  ///
  /// In en, this message translates to:
  /// **'Archive Session'**
  String get sessionActionsCloseTitle;

  /// No description provided for @sessionActionsClosing.
  ///
  /// In en, this message translates to:
  /// **'Archiving session...'**
  String get sessionActionsClosing;

  /// No description provided for @sessionActionsDeleteContent.
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to delete this session? This action cannot be undone.'**
  String get sessionActionsDeleteContent;

  /// No description provided for @sessionActionsDeleteTitle.
  ///
  /// In en, this message translates to:
  /// **'Delete Session'**
  String get sessionActionsDeleteTitle;

  /// No description provided for @sessionActionsDeleting.
  ///
  /// In en, this message translates to:
  /// **'Deleting session...'**
  String get sessionActionsDeleting;

  /// No description provided for @sessionActionsRenamePlaceholder.
  ///
  /// In en, this message translates to:
  /// **'Enter session name...'**
  String get sessionActionsRenamePlaceholder;

  /// No description provided for @sessionActionsRenameTitle.
  ///
  /// In en, this message translates to:
  /// **'Rename Session'**
  String get sessionActionsRenameTitle;

  /// No description provided for @sessionActionsRenaming.
  ///
  /// In en, this message translates to:
  /// **'Renaming session...'**
  String get sessionActionsRenaming;

  /// No description provided for @sessionInfoAgent.
  ///
  /// In en, this message translates to:
  /// **'Agent'**
  String get sessionInfoAgent;

  /// No description provided for @sessionInfoAiAgent.
  ///
  /// In en, this message translates to:
  /// **'AI Agent'**
  String get sessionInfoAiAgent;

  /// No description provided for @sessionInfoCopyId.
  ///
  /// In en, this message translates to:
  /// **'Copy ID'**
  String get sessionInfoCopyId;

  /// No description provided for @sessionInfoCreated.
  ///
  /// In en, this message translates to:
  /// **'Created'**
  String get sessionInfoCreated;

  /// No description provided for @sessionInfoDateAtTime.
  ///
  /// In en, this message translates to:
  /// **'{date} at {time}'**
  String sessionInfoDateAtTime(Object date, Object time);

  /// No description provided for @sessionInfoEditTitle.
  ///
  /// In en, this message translates to:
  /// **'Edit title'**
  String get sessionInfoEditTitle;

  /// No description provided for @sessionInfoId.
  ///
  /// In en, this message translates to:
  /// **'ID'**
  String get sessionInfoId;

  /// No description provided for @sessionInfoIdCopied.
  ///
  /// In en, this message translates to:
  /// **'Session ID copied to clipboard'**
  String get sessionInfoIdCopied;

  /// No description provided for @sessionInfoLastUpdated.
  ///
  /// In en, this message translates to:
  /// **'Last Updated'**
  String get sessionInfoLastUpdated;

  /// No description provided for @sessionInfoMachine.
  ///
  /// In en, this message translates to:
  /// **'Machine'**
  String get sessionInfoMachine;

  /// No description provided for @sessionInfoNameThisSession.
  ///
  /// In en, this message translates to:
  /// **'Name this session'**
  String get sessionInfoNameThisSession;

  /// No description provided for @sessionInfoProject.
  ///
  /// In en, this message translates to:
  /// **'Project'**
  String get sessionInfoProject;

  /// No description provided for @sessionInfoRenameFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to rename session'**
  String get sessionInfoRenameFailed;

  /// No description provided for @sessionInfoRenamed.
  ///
  /// In en, this message translates to:
  /// **'Session renamed'**
  String get sessionInfoRenamed;

  /// No description provided for @sessionInfoSessionInfo.
  ///
  /// In en, this message translates to:
  /// **'Session Info'**
  String get sessionInfoSessionInfo;

  /// No description provided for @sessionInfoSessionName.
  ///
  /// In en, this message translates to:
  /// **'Session Name'**
  String get sessionInfoSessionName;

  /// No description provided for @sessionInfoSourceApp.
  ///
  /// In en, this message translates to:
  /// **'App'**
  String get sessionInfoSourceApp;

  /// No description provided for @sessionInfoSourceTerminal.
  ///
  /// In en, this message translates to:
  /// **'Terminal'**
  String get sessionInfoSourceTerminal;

  /// No description provided for @sessionInfoStartedFrom.
  ///
  /// In en, this message translates to:
  /// **'Started From'**
  String get sessionInfoStartedFrom;

  /// No description provided for @sessionInfoViewMachine.
  ///
  /// In en, this message translates to:
  /// **'View machine'**
  String get sessionInfoViewMachine;

  /// No description provided for @sessionInfoWorktree.
  ///
  /// In en, this message translates to:
  /// **'Worktree'**
  String get sessionInfoWorktree;

  /// No description provided for @sessionListClosed.
  ///
  /// In en, this message translates to:
  /// **'Session archived'**
  String get sessionListClosed;

  /// No description provided for @sessionListDeleted.
  ///
  /// In en, this message translates to:
  /// **'Session deleted successfully'**
  String get sessionListDeleted;

  /// No description provided for @setupReminderNotificationBody.
  ///
  /// In en, this message translates to:
  /// **'Download the Vicoa desktop app on your computer and sign in — start using Claude Code, Codex, and OpenCode on the go.'**
  String get setupReminderNotificationBody;

  /// No description provided for @setupReminderNotificationTitle.
  ///
  /// In en, this message translates to:
  /// **'Bring coding agents to your phone 🚀'**
  String get setupReminderNotificationTitle;

  /// No description provided for @shareOptionsSheetCopiedToClipboard.
  ///
  /// In en, this message translates to:
  /// **'Content copied to clipboard'**
  String get shareOptionsSheetCopiedToClipboard;

  /// No description provided for @shareOptionsSheetCopyToClipboard.
  ///
  /// In en, this message translates to:
  /// **'Copy to clipboard'**
  String get shareOptionsSheetCopyToClipboard;

  /// No description provided for @shareOptionsSheetShareAs.
  ///
  /// In en, this message translates to:
  /// **'Share as'**
  String get shareOptionsSheetShareAs;

  /// No description provided for @shareOptionsSheetShareAsFile.
  ///
  /// In en, this message translates to:
  /// **'Share as a file'**
  String get shareOptionsSheetShareAsFile;

  /// No description provided for @shareOptionsSheetShareAsText.
  ///
  /// In en, this message translates to:
  /// **'Share as text'**
  String get shareOptionsSheetShareAsText;

  /// No description provided for @signInDialogBody.
  ///
  /// In en, this message translates to:
  /// **'Please sign in to use the feature.'**
  String get signInDialogBody;

  /// No description provided for @signInDialogLater.
  ///
  /// In en, this message translates to:
  /// **'I\'ll DO IT LATER'**
  String get signInDialogLater;

  /// No description provided for @signInDialogTitle.
  ///
  /// In en, this message translates to:
  /// **'Sign In To Continue'**
  String get signInDialogTitle;

  /// No description provided for @signUpAlreadyHaveAccount.
  ///
  /// In en, this message translates to:
  /// **'Already have an account? '**
  String get signUpAlreadyHaveAccount;

  /// No description provided for @signUpCreateAccount.
  ///
  /// In en, this message translates to:
  /// **'Create Account'**
  String get signUpCreateAccount;

  /// No description provided for @signUpDontHaveAccount.
  ///
  /// In en, this message translates to:
  /// **'Don\'t have an account? '**
  String get signUpDontHaveAccount;

  /// No description provided for @signUpEmailLabel.
  ///
  /// In en, this message translates to:
  /// **'Email address'**
  String get signUpEmailLabel;

  /// No description provided for @signUpHaveReferralCode.
  ///
  /// In en, this message translates to:
  /// **'I have a referral code'**
  String get signUpHaveReferralCode;

  /// No description provided for @signUpPasswordLabel.
  ///
  /// In en, this message translates to:
  /// **'Password'**
  String get signUpPasswordLabel;

  /// No description provided for @signUpPasswordsMismatch.
  ///
  /// In en, this message translates to:
  /// **'Passwords don\'t match!'**
  String get signUpPasswordsMismatch;

  /// No description provided for @signUpReferralCodeLabel.
  ///
  /// In en, this message translates to:
  /// **'Referral code (optional)'**
  String get signUpReferralCodeLabel;

  /// No description provided for @signUpReferralCreditsNotGrantedBody.
  ///
  /// In en, this message translates to:
  /// **'We couldn\'t grant your referral credits. Please contact us for support if you have any questions.'**
  String get signUpReferralCreditsNotGrantedBody;

  /// No description provided for @signUpReferralCreditsNotGrantedTitle.
  ///
  /// In en, this message translates to:
  /// **'Referral Credits Not Granted'**
  String get signUpReferralCreditsNotGrantedTitle;

  /// No description provided for @signUpReferralInvalidBody.
  ///
  /// In en, this message translates to:
  /// **'Your referral code doesn\'t seem to be valid. Please check it and try again later or remove it. If you have any questions, feel free to contact me at hi@vicoa.ai.'**
  String get signUpReferralInvalidBody;

  /// No description provided for @signUpReferralInvalidTitle.
  ///
  /// In en, this message translates to:
  /// **'Failed to Apply Referral Code'**
  String get signUpReferralInvalidTitle;

  /// No description provided for @signUpRemoveReferralCode.
  ///
  /// In en, this message translates to:
  /// **'Remove referral code'**
  String get signUpRemoveReferralCode;

  /// No description provided for @signUpSignInLink.
  ///
  /// In en, this message translates to:
  /// **'Sign in'**
  String get signUpSignInLink;

  /// No description provided for @signUpSignUpLink.
  ///
  /// In en, this message translates to:
  /// **'Sign up'**
  String get signUpSignUpLink;

  /// No description provided for @signUpSubtitleSignIn.
  ///
  /// In en, this message translates to:
  /// **'Sign in to {phrase} with AI coding agents anywhere you go'**
  String signUpSubtitleSignIn(Object phrase);

  /// No description provided for @signUpSubtitleSignUp.
  ///
  /// In en, this message translates to:
  /// **'Sign up to run a team of coding agents\nanywhere you go'**
  String get signUpSubtitleSignUp;

  /// No description provided for @startSessionAgent.
  ///
  /// In en, this message translates to:
  /// **'Agent'**
  String get startSessionAgent;

  /// No description provided for @startSessionAgentComingSoon.
  ///
  /// In en, this message translates to:
  /// **'{name} (Coming Soon)'**
  String startSessionAgentComingSoon(Object name);

  /// No description provided for @startSessionLoadingMachines.
  ///
  /// In en, this message translates to:
  /// **'Loading machines...'**
  String get startSessionLoadingMachines;

  /// No description provided for @startSessionMachine.
  ///
  /// In en, this message translates to:
  /// **'Machine'**
  String get startSessionMachine;

  /// No description provided for @startSessionNewSession.
  ///
  /// In en, this message translates to:
  /// **'New Session'**
  String get startSessionNewSession;

  /// No description provided for @startSessionOffline.
  ///
  /// In en, this message translates to:
  /// **'(offline)'**
  String get startSessionOffline;

  /// No description provided for @startSessionOrSeparator.
  ///
  /// In en, this message translates to:
  /// **' or '**
  String get startSessionOrSeparator;

  /// No description provided for @startSessionRecent.
  ///
  /// In en, this message translates to:
  /// **'Recent'**
  String get startSessionRecent;

  /// No description provided for @startSessionRunPrefix.
  ///
  /// In en, this message translates to:
  /// **'Run '**
  String get startSessionRunPrefix;

  /// No description provided for @startSessionSelectMachine.
  ///
  /// In en, this message translates to:
  /// **'Select a machine'**
  String get startSessionSelectMachine;

  /// No description provided for @startSessionShowMore.
  ///
  /// In en, this message translates to:
  /// **'Show more'**
  String get startSessionShowMore;

  /// No description provided for @startSessionStartSession.
  ///
  /// In en, this message translates to:
  /// **'Start Session'**
  String get startSessionStartSession;

  /// No description provided for @startSessionStartedNoStatus.
  ///
  /// In en, this message translates to:
  /// **'Session started but could not determine status. Please try again.'**
  String get startSessionStartedNoStatus;

  /// No description provided for @startSessionToBringOnline.
  ///
  /// In en, this message translates to:
  /// **' to bring your machine online.'**
  String get startSessionToBringOnline;

  /// No description provided for @startSessionUnableToStart.
  ///
  /// In en, this message translates to:
  /// **'Unable to Start Session'**
  String get startSessionUnableToStart;

  /// No description provided for @startSessionUnableToStartBody.
  ///
  /// In en, this message translates to:
  /// **'This could be due to:\n\n• The machine is not responding\n• Network connection issues\n• The directory path is invalid\n\nPlease check machine status and try again.'**
  String get startSessionUnableToStartBody;

  /// No description provided for @startSessionWorkingDirectory.
  ///
  /// In en, this message translates to:
  /// **'Working Directory'**
  String get startSessionWorkingDirectory;

  /// No description provided for @surveyDefaultQuestion.
  ///
  /// In en, this message translates to:
  /// **'What is your goal?'**
  String get surveyDefaultQuestion;

  /// No description provided for @surveyOpt1to2h.
  ///
  /// In en, this message translates to:
  /// **'1–2 hours'**
  String get surveyOpt1to2h;

  /// No description provided for @surveyOpt2to4h.
  ///
  /// In en, this message translates to:
  /// **'2–4 hours'**
  String get surveyOpt2to4h;

  /// No description provided for @surveyOpt4to8h.
  ///
  /// In en, this message translates to:
  /// **'4–8 hours'**
  String get surveyOpt4to8h;

  /// No description provided for @surveyOptCodePhone.
  ///
  /// In en, this message translates to:
  /// **'📱 I want to code from my phone'**
  String get surveyOptCodePhone;

  /// No description provided for @surveyOptDataScientist.
  ///
  /// In en, this message translates to:
  /// **'Data Scientist / Analyst'**
  String get surveyOptDataScientist;

  /// No description provided for @surveyOptResearcher.
  ///
  /// In en, this message translates to:
  /// **'Researcher'**
  String get surveyOptResearcher;

  /// No description provided for @surveyOptDesign.
  ///
  /// In en, this message translates to:
  /// **'Design'**
  String get surveyOptDesign;

  /// No description provided for @surveyOptDeveloper.
  ///
  /// In en, this message translates to:
  /// **'Developer'**
  String get surveyOptDeveloper;

  /// No description provided for @surveyOptFinance.
  ///
  /// In en, this message translates to:
  /// **'Finance'**
  String get surveyOptFinance;

  /// No description provided for @surveyOptFounder.
  ///
  /// In en, this message translates to:
  /// **'Founder'**
  String get surveyOptFounder;

  /// No description provided for @surveyOptFreelancer.
  ///
  /// In en, this message translates to:
  /// **'Freelancer'**
  String get surveyOptFreelancer;

  /// No description provided for @surveyOptGt8h.
  ///
  /// In en, this message translates to:
  /// **'>8 hours'**
  String get surveyOptGt8h;

  /// No description provided for @surveyOptLoseTrack.
  ///
  /// In en, this message translates to:
  /// **'🔀 I lose track of my agents\' work'**
  String get surveyOptLoseTrack;

  /// No description provided for @surveyOptLt1h.
  ///
  /// In en, this message translates to:
  /// **'<1 hour'**
  String get surveyOptLt1h;

  /// No description provided for @surveyOptMarketing.
  ///
  /// In en, this message translates to:
  /// **'Marketing'**
  String get surveyOptMarketing;

  /// No description provided for @surveyOptNoComputer.
  ///
  /// In en, this message translates to:
  /// **'I don\'t use computer'**
  String get surveyOptNoComputer;

  /// No description provided for @surveyOptNotAtComputer.
  ///
  /// In en, this message translates to:
  /// **'📍 I can\'t always be at my computer'**
  String get surveyOptNotAtComputer;

  /// No description provided for @surveyOptOthers.
  ///
  /// In en, this message translates to:
  /// **'Others'**
  String get surveyOptOthers;

  /// No description provided for @surveyOptProduct.
  ///
  /// In en, this message translates to:
  /// **'Product'**
  String get surveyOptProduct;

  /// No description provided for @surveyOptStuckDesk.
  ///
  /// In en, this message translates to:
  /// **'🖥️ I\'m stuck at my desk coding with AI'**
  String get surveyOptStuckDesk;

  /// No description provided for @surveyOptStudent.
  ///
  /// In en, this message translates to:
  /// **'Student'**
  String get surveyOptStudent;

  /// No description provided for @surveyOptTooManySessions.
  ///
  /// In en, this message translates to:
  /// **'🤯 I juggle too many coding sessions'**
  String get surveyOptTooManySessions;

  /// No description provided for @surveyOptWaitAi.
  ///
  /// In en, this message translates to:
  /// **'⏳ I often wait for AI to finish tasks'**
  String get surveyOptWaitAi;

  /// No description provided for @surveyQAiTools.
  ///
  /// In en, this message translates to:
  /// **'Which AI coding tools\ndo you use?'**
  String get surveyQAiTools;

  /// No description provided for @surveyQDailyTime.
  ///
  /// In en, this message translates to:
  /// **'How long do you\ncode with AI daily?'**
  String get surveyQDailyTime;

  /// No description provided for @surveyQDescribeYou.
  ///
  /// In en, this message translates to:
  /// **'Which best describes you?'**
  String get surveyQDescribeYou;

  /// No description provided for @surveyQOs.
  ///
  /// In en, this message translates to:
  /// **'Which operating system is\non your computer?'**
  String get surveyQOs;

  /// No description provided for @surveyQResonate.
  ///
  /// In en, this message translates to:
  /// **'Which of these do you\nresonate with?'**
  String get surveyQResonate;

  /// No description provided for @surveySelectAllThatApply.
  ///
  /// In en, this message translates to:
  /// **'Select all that apply'**
  String get surveySelectAllThatApply;

  /// No description provided for @surveyTypeYourAnswer.
  ///
  /// In en, this message translates to:
  /// **'Type your answer...'**
  String get surveyTypeYourAnswer;

  /// No description provided for @surveyWithImpactMotivationAlerts.
  ///
  /// In en, this message translates to:
  /// **'Perfect, Vicoa alerts you when AI finishes tasks.'**
  String get surveyWithImpactMotivationAlerts;

  /// No description provided for @surveyWithImpactMotivationCodeFromPhone.
  ///
  /// In en, this message translates to:
  /// **'Perfect, Vicoa is great for coding from your phone.'**
  String get surveyWithImpactMotivationCodeFromPhone;

  /// No description provided for @surveyWithImpactMotivationDefault.
  ///
  /// In en, this message translates to:
  /// **'Vicoa helps you code with AI on your phone.'**
  String get surveyWithImpactMotivationDefault;

  /// No description provided for @surveyWithImpactMotivationFreeFromDesk.
  ///
  /// In en, this message translates to:
  /// **'Perfect, Vicoa frees you from your desk to code on the go.'**
  String get surveyWithImpactMotivationFreeFromDesk;

  /// No description provided for @surveyWithImpactMotivationMultipleAgents.
  ///
  /// In en, this message translates to:
  /// **'Perfect, Vicoa is great for managing multiple agents.'**
  String get surveyWithImpactMotivationMultipleAgents;

  /// No description provided for @surveyWithImpactMotivationOnTrack.
  ///
  /// In en, this message translates to:
  /// **'Perfect, Vicoa keeps you on track of your agents.'**
  String get surveyWithImpactMotivationOnTrack;

  /// No description provided for @surveyWithImpactMotivationSendCommands.
  ///
  /// In en, this message translates to:
  /// **'Perfect, Vicoa notifies you and allows you to send commands from your phone.'**
  String get surveyWithImpactMotivationSendCommands;

  /// No description provided for @tutorialTitle.
  ///
  /// In en, this message translates to:
  /// **'Tutorials'**
  String get tutorialTitle;

  /// No description provided for @usageCreditsCanStillSend.
  ///
  /// In en, this message translates to:
  /// **'You can still send {count} messages for free.'**
  String usageCreditsCanStillSend(Object count);

  /// No description provided for @usageCreditsFreeMessages.
  ///
  /// In en, this message translates to:
  /// **'Free Messages'**
  String get usageCreditsFreeMessages;

  /// No description provided for @usageCreditsGetMoreFreeMessages.
  ///
  /// In en, this message translates to:
  /// **'Get more free messages'**
  String get usageCreditsGetMoreFreeMessages;

  /// No description provided for @usageCreditsGiftComingSoon.
  ///
  /// In en, this message translates to:
  /// **'Coming soon: gift your free messages to friends!'**
  String get usageCreditsGiftComingSoon;

  /// No description provided for @usageCreditsInviteFriends.
  ///
  /// In en, this message translates to:
  /// **'Invite Friends'**
  String get usageCreditsInviteFriends;

  /// No description provided for @usageCreditsLearnMore.
  ///
  /// In en, this message translates to:
  /// **'Learn More'**
  String get usageCreditsLearnMore;

  /// No description provided for @usageCreditsRateUs5Stars.
  ///
  /// In en, this message translates to:
  /// **'Rate Us 5 Stars'**
  String get usageCreditsRateUs5Stars;

  /// No description provided for @usageCreditsStartFreeTrialNow.
  ///
  /// In en, this message translates to:
  /// **'Start Free Trial Now 👋'**
  String get usageCreditsStartFreeTrialNow;

  /// No description provided for @usageCreditsUnlimitedMessagesAgents.
  ///
  /// In en, this message translates to:
  /// **'Unlimited Messages & Agents'**
  String get usageCreditsUnlimitedMessagesAgents;

  /// No description provided for @usageCreditsYourMessages.
  ///
  /// In en, this message translates to:
  /// **'Your Messages'**
  String get usageCreditsYourMessages;

  /// No description provided for @versionUpdateDialogBody.
  ///
  /// In en, this message translates to:
  /// **'A new version of Vicoa is available. Please update your app to use all of our amazing features.'**
  String get versionUpdateDialogBody;

  /// No description provided for @versionUpdateDialogLater.
  ///
  /// In en, this message translates to:
  /// **'I\'ll DO IT LATER'**
  String get versionUpdateDialogLater;

  /// No description provided for @versionUpdateDialogTitle.
  ///
  /// In en, this message translates to:
  /// **'New version available'**
  String get versionUpdateDialogTitle;

  /// No description provided for @versionUpdateDialogUpdateNow.
  ///
  /// In en, this message translates to:
  /// **'UPDATE NOW'**
  String get versionUpdateDialogUpdateNow;

  /// No description provided for @videoPlayerXError.
  ///
  /// In en, this message translates to:
  /// **'Error playing video'**
  String get videoPlayerXError;

  /// No description provided for @videoPlayerXLoading.
  ///
  /// In en, this message translates to:
  /// **'Loading'**
  String get videoPlayerXLoading;

  /// No description provided for @voiceAssistanceDescription.
  ///
  /// In en, this message translates to:
  /// **'Choose the language for voice dictation in chat.'**
  String get voiceAssistanceDescription;

  /// No description provided for @voiceAssistanceTitle.
  ///
  /// In en, this message translates to:
  /// **'Voice Assistance'**
  String get voiceAssistanceTitle;

  /// No description provided for @voiceAssistanceTranscriptionLanguage.
  ///
  /// In en, this message translates to:
  /// **'Transcription Language'**
  String get voiceAssistanceTranscriptionLanguage;

  /// No description provided for @voiceLanguageSearchHint.
  ///
  /// In en, this message translates to:
  /// **'Search language'**
  String get voiceLanguageSearchHint;

  /// No description provided for @voiceLanguageTitle.
  ///
  /// In en, this message translates to:
  /// **'Voice Language'**
  String get voiceLanguageTitle;

  /// No description provided for @webPreviewBeta.
  ///
  /// In en, this message translates to:
  /// **'beta'**
  String get webPreviewBeta;

  /// No description provided for @webPreviewEnterUrl.
  ///
  /// In en, this message translates to:
  /// **'Enter URL'**
  String get webPreviewEnterUrl;

  /// No description provided for @webPreviewHttpStatus.
  ///
  /// In en, this message translates to:
  /// **'The server returned HTTP {statusCode}.'**
  String webPreviewHttpStatus(Object statusCode);

  /// No description provided for @webPreviewSiteUnreachable.
  ///
  /// In en, this message translates to:
  /// **'This site can\'t be reached'**
  String get webPreviewSiteUnreachable;

  /// No description provided for @webPreviewTitle.
  ///
  /// In en, this message translates to:
  /// **'Live Preview'**
  String get webPreviewTitle;

  /// No description provided for @webPreviewUrlUnreachableDetails.
  ///
  /// In en, this message translates to:
  /// **'This URL could not be reached. {details}'**
  String webPreviewUrlUnreachableDetails(Object details);

  /// No description provided for @webPreviewUrlUnreachableHint.
  ///
  /// In en, this message translates to:
  /// **'This URL could not be reached. Check that the preview server is running and the tunnel URL is still valid.'**
  String get webPreviewUrlUnreachableHint;

  /// No description provided for @webPreviewWebUnavailable.
  ///
  /// In en, this message translates to:
  /// **'Web preview is available on iOS/Android app builds.'**
  String get webPreviewWebUnavailable;

  /// No description provided for @welcomeAnswerQuickQuestions.
  ///
  /// In en, this message translates to:
  /// **'Answer a few quick questions to personalize your experience'**
  String get welcomeAnswerQuickQuestions;

  /// No description provided for @welcomeDemoCancelSubscription.
  ///
  /// In en, this message translates to:
  /// **'Heads up: Vicoa needs a computer to run, so if you\'re on a trial you may want to **cancel it to avoid charges**.\n\n[How to cancel your subscription →]({url})'**
  String welcomeDemoCancelSubscription(Object url);

  /// No description provided for @welcomeDemoCardTapToSee.
  ///
  /// In en, this message translates to:
  /// **'Tap to see how Vicoa works'**
  String get welcomeDemoCardTapToSee;

  /// No description provided for @welcomeDemoCardWelcome.
  ///
  /// In en, this message translates to:
  /// **'Welcome to Vicoa'**
  String get welcomeDemoCardWelcome;

  /// No description provided for @welcomeDemoCta.
  ///
  /// In en, this message translates to:
  /// **'Ready to try it for real? Pick what fits you:'**
  String get welcomeDemoCta;

  /// No description provided for @welcomeDemoInstanceName.
  ///
  /// In en, this message translates to:
  /// **'Welcome to Vicoa 👋'**
  String get welcomeDemoInstanceName;

  /// No description provided for @welcomeDemoLatestMessage.
  ///
  /// In en, this message translates to:
  /// **'Ready when you are — pick how you want to start.'**
  String get welcomeDemoLatestMessage;

  /// No description provided for @welcomeDemoMsg1.
  ///
  /// In en, this message translates to:
  /// **'👋 **Welcome to Vicoa!**\n\nVicoa lets you orchestrate dozens of coding agents in parallel, anywhere. \n\nThis sample chat shows what a coding session looks like after you start using Vicoa.👇'**
  String get welcomeDemoMsg1;

  /// No description provided for @welcomeDemoMsg2.
  ///
  /// In en, this message translates to:
  /// **'How do I use Vicoa?'**
  String get welcomeDemoMsg2;

  /// No description provided for @welcomeDemoMsg3.
  ///
  /// In en, this message translates to:
  /// **'📱 **Start from phone**: tap **+** button, start a new coding session.\n\n🖥️ **Start from computer**: start coding at your desk, continue on the phone.\n'**
  String get welcomeDemoMsg3;

  /// No description provided for @welcomeDemoMsg4.
  ///
  /// In en, this message translates to:
  /// **'What can I do?'**
  String get welcomeDemoMsg4;

  /// No description provided for @welcomeDemoMsg5.
  ///
  /// In en, this message translates to:
  /// **'- 💬 Chat with your agent\n- 🔔 Get notified when tasks done\n- ✅ Approve actions\n- 👀 See code changes\n- And many more...'**
  String get welcomeDemoMsg5;

  /// No description provided for @welcomeDemoMsg8.
  ///
  /// In en, this message translates to:
  /// **'Which agents work with Vicoa?'**
  String get welcomeDemoMsg8;

  /// No description provided for @welcomeDemoMsg9.
  ///
  /// In en, this message translates to:
  /// **'Whichever you already use:\n| Agent | Models |\n| --- | --- |\n| Claude Code | e.g., Opus 4.8, Opus 4.7, Sonnet 4.6 |\n| Codex | e.g., GPT-5.5, GPT-5.4 |\n| OpenCode | e.g., Z.AI, Minimax, DeepSeek |\n| Gemini | e.g., Gemini 3 Pro, Gemini 2.5 Flash |\n| Cursor | e.g., Composer, Claude, GPT |\n| Copilot | e.g., Claude, GPT, Gemini |\n| Kimi | e.g., Kimi K2.5, K2.6, K2.7 Code |\n| Hermes | 50+ models |\n\n> You bring your own agent, Vicoa just connects it.\n\nCoding agents make changes, Vicoa show you in real-time: \n\n'**
  String get welcomeDemoMsg9;

  /// No description provided for @welcomeDemoNoComputerSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Tell us what you want instead'**
  String get welcomeDemoNoComputerSubtitle;

  /// No description provided for @welcomeDemoNoComputerTitle.
  ///
  /// In en, this message translates to:
  /// **'I don\'t have a computer with me'**
  String get welcomeDemoNoComputerTitle;

  /// No description provided for @welcomeDemoSetupCliSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Email me a get-started link'**
  String get welcomeDemoSetupCliSubtitle;

  /// No description provided for @welcomeDemoSetupCliTitle.
  ///
  /// In en, this message translates to:
  /// **'I\'ll set up Vicoa on my computer'**
  String get welcomeDemoSetupCliTitle;

  /// No description provided for @welcomeDemoSetupEmailSent.
  ///
  /// In en, this message translates to:
  /// **'📧 We\'ve sent a get-started link to {target}.\n\n'**
  String welcomeDemoSetupEmailSent(Object target);

  /// No description provided for @welcomeDemoSetupEmailTargetFallback.
  ///
  /// In en, this message translates to:
  /// **'your inbox'**
  String get welcomeDemoSetupEmailTargetFallback;

  /// No description provided for @welcomeDemoSetupInstructions.
  ///
  /// In en, this message translates to:
  /// **'Here\'s how to get set up on your computer:\n\n1. Download the desktop app: **https://vicoa.ai/download**\n2. Open it and sign in with this account. Your computer and phone are connected automatically\n\nPrefer the command line? Follow the [setup guide](https://vicoa.ai/docs/getting-started).\n\nHappy building!\n'**
  String get welcomeDemoSetupInstructions;

  /// No description provided for @welcomeDemoSetupQuestion.
  ///
  /// In en, this message translates to:
  /// **'How do I start?'**
  String get welcomeDemoSetupQuestion;

  /// No description provided for @welcomeDemoWaitlistHeader.
  ///
  /// In en, this message translates to:
  /// **'Quick question'**
  String get welcomeDemoWaitlistHeader;

  /// No description provided for @welcomeDemoWaitlistIntro.
  ///
  /// In en, this message translates to:
  /// **'No problem. Vicoa needs a computer today, but we\'re working on more. Tell us what you\'re after and we\'ll keep you posted:'**
  String get welcomeDemoWaitlistIntro;

  /// No description provided for @welcomeDemoWaitlistOptDev.
  ///
  /// In en, this message translates to:
  /// **'I\'m a developer. My computer is not with me right now'**
  String get welcomeDemoWaitlistOptDev;

  /// No description provided for @welcomeDemoWaitlistOptGithub.
  ///
  /// In en, this message translates to:
  /// **'I\'m a developer. I want to connect GitHub and work fully from my phone'**
  String get welcomeDemoWaitlistOptGithub;

  /// No description provided for @welcomeDemoWaitlistOptNotDev.
  ///
  /// In en, this message translates to:
  /// **'I\'m not a developer. I just want to build apps on my phone'**
  String get welcomeDemoWaitlistOptNotDev;

  /// No description provided for @welcomeDemoWaitlistPrompt.
  ///
  /// In en, this message translates to:
  /// **'Join the waitlist'**
  String get welcomeDemoWaitlistPrompt;

  /// No description provided for @welcomeDemoWaitlistQuestion.
  ///
  /// In en, this message translates to:
  /// **'What do you want to do with Vicoa?'**
  String get welcomeDemoWaitlistQuestion;

  /// No description provided for @welcomeDemoWaitlistThanks.
  ///
  /// In en, this message translates to:
  /// **'🙌 Thank you! You\'re on the list. We\'ll reach out as soon as there\'s a great way for you to get started.'**
  String get welcomeDemoWaitlistThanks;

  /// No description provided for @welcomeGladToHaveYou.
  ///
  /// In en, this message translates to:
  /// **'Glad to have you with us 👋'**
  String get welcomeGladToHaveYou;

  /// No description provided for @welcomeSkipForNow.
  ///
  /// In en, this message translates to:
  /// **'Skip for now'**
  String get welcomeSkipForNow;

  /// No description provided for @welcomeStartYourJourney.
  ///
  /// In en, this message translates to:
  /// **'Let\'s start your journey to \nvibe code anywhere.'**
  String get welcomeStartYourJourney;

  /// No description provided for @worktreeActionsActiveSession.
  ///
  /// In en, this message translates to:
  /// **'A session is still running in this worktree.'**
  String get worktreeActionsActiveSession;

  /// No description provided for @worktreeActionsCleanupContent.
  ///
  /// In en, this message translates to:
  /// **'This session ran in a vicoa worktree with no remaining changes. Delete the worktree, or keep the files?'**
  String get worktreeActionsCleanupContent;

  /// No description provided for @worktreeActionsCleanupTitle.
  ///
  /// In en, this message translates to:
  /// **'Delete worktree?'**
  String get worktreeActionsCleanupTitle;

  /// No description provided for @worktreeActionsDeleted.
  ///
  /// In en, this message translates to:
  /// **'Worktree deleted.'**
  String get worktreeActionsDeleted;

  /// No description provided for @worktreeActionsRemoveContent.
  ///
  /// In en, this message translates to:
  /// **'Remove the worktree \"{branch}\"? The branch is kept, so commits on it stay safe.'**
  String worktreeActionsRemoveContent(Object branch);

  /// No description provided for @worktreeActionsRemoveDirtyContent.
  ///
  /// In en, this message translates to:
  /// **'The worktree \"{branch}\" has uncommitted changes. Remove it anyway? The branch is kept, so any commits on it stay safe.'**
  String worktreeActionsRemoveDirtyContent(Object branch);

  /// No description provided for @worktreeActionsRemoveFailed.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t remove worktree.'**
  String get worktreeActionsRemoveFailed;

  /// No description provided for @worktreeActionsRemoveFailedCode.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t remove worktree: {code}'**
  String worktreeActionsRemoveFailedCode(Object code);

  /// No description provided for @worktreeActionsRemoveTitle.
  ///
  /// In en, this message translates to:
  /// **'Remove worktree'**
  String get worktreeActionsRemoveTitle;

  /// No description provided for @worktreeActionsRemoved.
  ///
  /// In en, this message translates to:
  /// **'Worktree removed.'**
  String get worktreeActionsRemoved;

  /// No description provided for @worktreeActionsThisWorktree.
  ///
  /// In en, this message translates to:
  /// **'this worktree'**
  String get worktreeActionsThisWorktree;

  /// No description provided for @worktreeDetailBranch.
  ///
  /// In en, this message translates to:
  /// **'Branch'**
  String get worktreeDetailBranch;

  /// No description provided for @worktreeDetailCopyPath.
  ///
  /// In en, this message translates to:
  /// **'Copy path'**
  String get worktreeDetailCopyPath;

  /// No description provided for @worktreeDetailInUseDescription.
  ///
  /// In en, this message translates to:
  /// **'A session is still running in this worktree. End it before removing.'**
  String get worktreeDetailInUseDescription;

  /// No description provided for @worktreeDetailNotManagedNote.
  ///
  /// In en, this message translates to:
  /// **'This worktree wasn\'t created by Vicoa, so it can\'t be managed from the app.'**
  String get worktreeDetailNotManagedNote;

  /// No description provided for @worktreeDetailOrigin.
  ///
  /// In en, this message translates to:
  /// **'Origin'**
  String get worktreeDetailOrigin;

  /// No description provided for @worktreeDetailOriginExternal.
  ///
  /// In en, this message translates to:
  /// **'External'**
  String get worktreeDetailOriginExternal;

  /// No description provided for @worktreeDetailOriginVicoa.
  ///
  /// In en, this message translates to:
  /// **'Vicoa'**
  String get worktreeDetailOriginVicoa;

  /// No description provided for @worktreeDetailPath.
  ///
  /// In en, this message translates to:
  /// **'Path'**
  String get worktreeDetailPath;

  /// No description provided for @worktreeDetailPathCopied.
  ///
  /// In en, this message translates to:
  /// **'Path copied to clipboard'**
  String get worktreeDetailPathCopied;

  /// No description provided for @worktreeDetailRemoveDescription.
  ///
  /// In en, this message translates to:
  /// **'Removes the worktree\'s checkout. The branch is kept, so commits stay safe.'**
  String get worktreeDetailRemoveDescription;

  /// No description provided for @worktreeDetailRemoveWorktree.
  ///
  /// In en, this message translates to:
  /// **'Remove worktree'**
  String get worktreeDetailRemoveWorktree;

  /// No description provided for @worktreeDetailStatus.
  ///
  /// In en, this message translates to:
  /// **'Status'**
  String get worktreeDetailStatus;

  /// No description provided for @worktreeDetailStatusIdle.
  ///
  /// In en, this message translates to:
  /// **'Idle'**
  String get worktreeDetailStatusIdle;

  /// No description provided for @worktreeDetailStatusInUse.
  ///
  /// In en, this message translates to:
  /// **'In use, a session is running'**
  String get worktreeDetailStatusInUse;

  /// No description provided for @worktreeDetailWorktree.
  ///
  /// In en, this message translates to:
  /// **'Worktree'**
  String get worktreeDetailWorktree;

  /// No description provided for @worktreePickerCurrentBranch.
  ///
  /// In en, this message translates to:
  /// **'Current branch'**
  String get worktreePickerCurrentBranch;

  /// No description provided for @worktreePickerCurrentBranchSubtitle.
  ///
  /// In en, this message translates to:
  /// **'No worktree · run in the directory'**
  String get worktreePickerCurrentBranchSubtitle;

  /// No description provided for @worktreePickerDetached.
  ///
  /// In en, this message translates to:
  /// **'(detached)'**
  String get worktreePickerDetached;

  /// No description provided for @worktreePickerExistingWorktrees.
  ///
  /// In en, this message translates to:
  /// **'Existing worktrees'**
  String get worktreePickerExistingWorktrees;

  /// No description provided for @worktreePickerExternalPath.
  ///
  /// In en, this message translates to:
  /// **'{path} · external'**
  String worktreePickerExternalPath(Object path);

  /// No description provided for @worktreePickerLoadFailed.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t load worktrees'**
  String get worktreePickerLoadFailed;

  /// No description provided for @worktreePickerNewWorktree.
  ///
  /// In en, this message translates to:
  /// **'New worktree'**
  String get worktreePickerNewWorktree;

  /// No description provided for @worktreePickerNewWorktreeSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Fork a fresh branch off HEAD'**
  String get worktreePickerNewWorktreeSubtitle;

  /// No description provided for @worktreePickerNotARepo.
  ///
  /// In en, this message translates to:
  /// **'This directory isn\'t a git repository — only the current branch is available.'**
  String get worktreePickerNotARepo;

  /// No description provided for @worktreePickerWorktree.
  ///
  /// In en, this message translates to:
  /// **'Worktree'**
  String get worktreePickerWorktree;

  /// No description provided for @worktreesCouldNotLoad.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t load worktrees'**
  String get worktreesCouldNotLoad;

  /// No description provided for @worktreesDetached.
  ///
  /// In en, this message translates to:
  /// **'(detached)'**
  String get worktreesDetached;

  /// No description provided for @worktreesNoWorktreesSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Start a session in a new worktree to create one. It\'ll show up here for you to manage.'**
  String get worktreesNoWorktreesSubtitle;

  /// No description provided for @worktreesNoWorktreesYet.
  ///
  /// In en, this message translates to:
  /// **'No worktrees yet'**
  String get worktreesNoWorktreesYet;

  /// No description provided for @worktreesNotAGitRepo.
  ///
  /// In en, this message translates to:
  /// **'Not a git repository'**
  String get worktreesNotAGitRepo;

  /// No description provided for @worktreesNotAGitRepoSubtitle.
  ///
  /// In en, this message translates to:
  /// **'This directory isn\'t a git repository.'**
  String get worktreesNotAGitRepoSubtitle;

  /// No description provided for @worktreesPullToRefresh.
  ///
  /// In en, this message translates to:
  /// **'Pull to refresh to try again.'**
  String get worktreesPullToRefresh;

  /// No description provided for @worktreesTitle.
  ///
  /// In en, this message translates to:
  /// **'Worktrees'**
  String get worktreesTitle;

  /// No description provided for @worktreesWorktreeRemoved.
  ///
  /// In en, this message translates to:
  /// **'Worktree removed.'**
  String get worktreesWorktreeRemoved;

  /// No description provided for @youtubeXInvalidUrl.
  ///
  /// In en, this message translates to:
  /// **'Invalid YouTube URL'**
  String get youtubeXInvalidUrl;

  /// No description provided for @youtubeXNoVideoUrl.
  ///
  /// In en, this message translates to:
  /// **'No video URL provided'**
  String get youtubeXNoVideoUrl;

  /// No description provided for @sessionUsageTitle.
  ///
  /// In en, this message translates to:
  /// **'Usage'**
  String get sessionUsageTitle;

  /// No description provided for @sessionUsageContext.
  ///
  /// In en, this message translates to:
  /// **'Context Window'**
  String get sessionUsageContext;

  /// No description provided for @sessionUsageTokensSuffix.
  ///
  /// In en, this message translates to:
  /// **'tokens'**
  String get sessionUsageTokensSuffix;

  /// No description provided for @sessionUsageSessionCost.
  ///
  /// In en, this message translates to:
  /// **'Session cost {cost}'**
  String sessionUsageSessionCost(Object cost);

  /// No description provided for @sessionUsageCredits.
  ///
  /// In en, this message translates to:
  /// **'Credits'**
  String get sessionUsageCredits;

  /// No description provided for @sessionUsageCreditsLeft.
  ///
  /// In en, this message translates to:
  /// **'{amount} left'**
  String sessionUsageCreditsLeft(Object amount);

  /// No description provided for @sessionUsageResetsAtTime.
  ///
  /// In en, this message translates to:
  /// **'Resets {time}'**
  String sessionUsageResetsAtTime(Object time);

  /// No description provided for @sessionUsageResetsOnDate.
  ///
  /// In en, this message translates to:
  /// **'Resets {date} at {time}'**
  String sessionUsageResetsOnDate(Object date, Object time);

  /// No description provided for @sessionUsageResettingNow.
  ///
  /// In en, this message translates to:
  /// **'Resetting now'**
  String get sessionUsageResettingNow;

  /// No description provided for @sessionUsageRefreshing.
  ///
  /// In en, this message translates to:
  /// **'Refreshing…'**
  String get sessionUsageRefreshing;

  /// No description provided for @automationsAgent.
  ///
  /// In en, this message translates to:
  /// **'Agent'**
  String get automationsAgent;

  /// No description provided for @automationsAtMinute.
  ///
  /// In en, this message translates to:
  /// **'At minute'**
  String get automationsAtMinute;

  /// No description provided for @automationsChooseFolder.
  ///
  /// In en, this message translates to:
  /// **'Choose folder'**
  String get automationsChooseFolder;

  /// No description provided for @automationsConnectMachineFirst.
  ///
  /// In en, this message translates to:
  /// **'Connect a machine first to create an automation.'**
  String get automationsConnectMachineFirst;

  /// No description provided for @automationsCouldNotLoad.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t load automations'**
  String get automationsCouldNotLoad;

  /// No description provided for @automationsDate.
  ///
  /// In en, this message translates to:
  /// **'Date'**
  String get automationsDate;

  /// No description provided for @automationsDelete.
  ///
  /// In en, this message translates to:
  /// **'Delete'**
  String get automationsDelete;

  /// No description provided for @automationsDeleteConfirmBody.
  ///
  /// In en, this message translates to:
  /// **'This removes the automation and its run history. Sessions it already started are kept.'**
  String get automationsDeleteConfirmBody;

  /// No description provided for @automationsDeleteConfirmTitle.
  ///
  /// In en, this message translates to:
  /// **'Delete automation?'**
  String get automationsDeleteConfirmTitle;

  /// No description provided for @automationsDeleted.
  ///
  /// In en, this message translates to:
  /// **'Automation deleted'**
  String get automationsDeleted;

  /// No description provided for @automationsEditTitle.
  ///
  /// In en, this message translates to:
  /// **'Edit Automation'**
  String get automationsEditTitle;

  /// No description provided for @automationsEmptySubtitle.
  ///
  /// In en, this message translates to:
  /// **'Schedule an agent to run on automatically.'**
  String get automationsEmptySubtitle;

  /// No description provided for @automationsEmptyTitle.
  ///
  /// In en, this message translates to:
  /// **'No automations yet'**
  String get automationsEmptyTitle;

  /// No description provided for @automationsEvery.
  ///
  /// In en, this message translates to:
  /// **'Every'**
  String get automationsEvery;

  /// No description provided for @automationsEveryUnitDays.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{day} other{days}}'**
  String automationsEveryUnitDays(int count);

  /// No description provided for @automationsEveryUnitHours.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{hour} other{hours}}'**
  String automationsEveryUnitHours(int count);

  /// No description provided for @automationsEveryUnitMinutes.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{minute} other{minutes}}'**
  String automationsEveryUnitMinutes(int count);

  /// No description provided for @automationsEveryUnitMonths.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{month} other{months}}'**
  String automationsEveryUnitMonths(int count);

  /// No description provided for @automationsEveryUnitWeeks.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{week} other{weeks}}'**
  String automationsEveryUnitWeeks(int count);

  /// No description provided for @automationsFilterActive.
  ///
  /// In en, this message translates to:
  /// **'Active'**
  String get automationsFilterActive;

  /// No description provided for @automationsFilterAll.
  ///
  /// In en, this message translates to:
  /// **'All'**
  String get automationsFilterAll;

  /// No description provided for @automationsFilterPaused.
  ///
  /// In en, this message translates to:
  /// **'Paused'**
  String get automationsFilterPaused;

  /// No description provided for @automationsMachineOffline.
  ///
  /// In en, this message translates to:
  /// **'Machine is offline — run could not start.'**
  String get automationsMachineOffline;

  /// No description provided for @automationsNew.
  ///
  /// In en, this message translates to:
  /// **'New Automation'**
  String get automationsNew;

  /// No description provided for @automationsNextRun.
  ///
  /// In en, this message translates to:
  /// **'Next · {when}'**
  String automationsNextRun(String when);

  /// No description provided for @automationsNoRunsYet.
  ///
  /// In en, this message translates to:
  /// **'No runs yet.'**
  String get automationsNoRunsYet;

  /// No description provided for @automationsPause.
  ///
  /// In en, this message translates to:
  /// **'Pause'**
  String get automationsPause;

  /// No description provided for @automationsProject.
  ///
  /// In en, this message translates to:
  /// **'Project'**
  String get automationsProject;

  /// No description provided for @automationsPromptPlaceholder.
  ///
  /// In en, this message translates to:
  /// **'Describe what the agent should do'**
  String get automationsPromptPlaceholder;

  /// No description provided for @automationsPullToRefresh.
  ///
  /// In en, this message translates to:
  /// **'Pull down to try again'**
  String get automationsPullToRefresh;

  /// No description provided for @automationsRepeat.
  ///
  /// In en, this message translates to:
  /// **'Repeat'**
  String get automationsRepeat;

  /// No description provided for @automationsRepeatCustom.
  ///
  /// In en, this message translates to:
  /// **'Custom'**
  String get automationsRepeatCustom;

  /// No description provided for @automationsRepeatDaily.
  ///
  /// In en, this message translates to:
  /// **'Daily'**
  String get automationsRepeatDaily;

  /// No description provided for @automationsRepeatHourly.
  ///
  /// In en, this message translates to:
  /// **'Hourly'**
  String get automationsRepeatHourly;

  /// No description provided for @automationsRepeatMinutely.
  ///
  /// In en, this message translates to:
  /// **'Minutely'**
  String get automationsRepeatMinutely;

  /// No description provided for @automationsRepeatMonthly.
  ///
  /// In en, this message translates to:
  /// **'Monthly'**
  String get automationsRepeatMonthly;

  /// No description provided for @automationsRepeatOnce.
  ///
  /// In en, this message translates to:
  /// **'Once'**
  String get automationsRepeatOnce;

  /// No description provided for @automationsRepeatWeekdays.
  ///
  /// In en, this message translates to:
  /// **'Weekdays'**
  String get automationsRepeatWeekdays;

  /// No description provided for @automationsRepeatWeekly.
  ///
  /// In en, this message translates to:
  /// **'Weekly'**
  String get automationsRepeatWeekly;

  /// No description provided for @automationsRepeats.
  ///
  /// In en, this message translates to:
  /// **'Repeats'**
  String get automationsRepeats;

  /// No description provided for @automationsResume.
  ///
  /// In en, this message translates to:
  /// **'Resume'**
  String get automationsResume;

  /// No description provided for @automationsRunFailed.
  ///
  /// In en, this message translates to:
  /// **'Run failed'**
  String get automationsRunFailed;

  /// No description provided for @automationsRunNow.
  ///
  /// In en, this message translates to:
  /// **'Run now'**
  String get automationsRunNow;

  /// No description provided for @automationsRunStarted.
  ///
  /// In en, this message translates to:
  /// **'Run started'**
  String get automationsRunStarted;

  /// No description provided for @automationsRunStatusFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed'**
  String get automationsRunStatusFailed;

  /// No description provided for @automationsRunStatusFired.
  ///
  /// In en, this message translates to:
  /// **'Ran'**
  String get automationsRunStatusFired;

  /// No description provided for @automationsRunStatusMissedOffline.
  ///
  /// In en, this message translates to:
  /// **'Missed — offline'**
  String get automationsRunStatusMissedOffline;

  /// No description provided for @automationsRunStatusSkipped.
  ///
  /// In en, this message translates to:
  /// **'Skipped'**
  String get automationsRunStatusSkipped;

  /// No description provided for @automationsRunsOn.
  ///
  /// In en, this message translates to:
  /// **'Runs on'**
  String get automationsRunsOn;

  /// No description provided for @automationsSaveFailed.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t save automation'**
  String get automationsSaveFailed;

  /// No description provided for @automationsScheduleOnceAt.
  ///
  /// In en, this message translates to:
  /// **'Once · {when}'**
  String automationsScheduleOnceAt(String when);

  /// No description provided for @automationsSectionDetails.
  ///
  /// In en, this message translates to:
  /// **'Details'**
  String get automationsSectionDetails;

  /// No description provided for @automationsSectionFrequency.
  ///
  /// In en, this message translates to:
  /// **'Frequency'**
  String get automationsSectionFrequency;

  /// No description provided for @automationsSectionRunHistory.
  ///
  /// In en, this message translates to:
  /// **'Run history'**
  String get automationsSectionRunHistory;

  /// No description provided for @automationsStatusPaused.
  ///
  /// In en, this message translates to:
  /// **'Paused'**
  String get automationsStatusPaused;

  /// No description provided for @automationsSummaryDaily.
  ///
  /// In en, this message translates to:
  /// **'Daily at {time}'**
  String automationsSummaryDaily(String time);

  /// No description provided for @automationsSummaryEveryDays.
  ///
  /// In en, this message translates to:
  /// **'Every {n} days at {time}'**
  String automationsSummaryEveryDays(String n, String time);

  /// No description provided for @automationsSummaryEveryHours.
  ///
  /// In en, this message translates to:
  /// **'Every {n} hours at :{minute}'**
  String automationsSummaryEveryHours(String n, String minute);

  /// No description provided for @automationsSummaryEveryMonths.
  ///
  /// In en, this message translates to:
  /// **'Every {n} months on day {days} at {time}'**
  String automationsSummaryEveryMonths(String n, String days, String time);

  /// No description provided for @automationsSummaryEveryWeeks.
  ///
  /// In en, this message translates to:
  /// **'Every {n} weeks on {days} at {time}'**
  String automationsSummaryEveryWeeks(String n, String days, String time);

  /// No description provided for @automationsSummaryHourly.
  ///
  /// In en, this message translates to:
  /// **'Hourly at :{minute}'**
  String automationsSummaryHourly(String minute);

  /// No description provided for @automationsSummaryHourlyPlain.
  ///
  /// In en, this message translates to:
  /// **'Hourly'**
  String get automationsSummaryHourlyPlain;

  /// No description provided for @automationsSummaryEveryHoursPlain.
  ///
  /// In en, this message translates to:
  /// **'Every {n} hours'**
  String automationsSummaryEveryHoursPlain(String n);

  /// No description provided for @automationsSummaryEveryMinutes.
  ///
  /// In en, this message translates to:
  /// **'Every {n} minutes'**
  String automationsSummaryEveryMinutes(String n);

  /// No description provided for @automationsSummaryRecurring.
  ///
  /// In en, this message translates to:
  /// **'Recurring'**
  String get automationsSummaryRecurring;

  /// No description provided for @automationsSummaryWeekdays.
  ///
  /// In en, this message translates to:
  /// **'Weekdays at {time}'**
  String automationsSummaryWeekdays(String time);

  /// No description provided for @automationsSummaryWeekly.
  ///
  /// In en, this message translates to:
  /// **'Weekly on {days} at {time}'**
  String automationsSummaryWeekly(String days, String time);

  /// No description provided for @automationsTime.
  ///
  /// In en, this message translates to:
  /// **'Time'**
  String get automationsTime;

  /// No description provided for @automationsTimeWindow.
  ///
  /// In en, this message translates to:
  /// **'Time window'**
  String get automationsTimeWindow;

  /// No description provided for @automationsWindowAllDay.
  ///
  /// In en, this message translates to:
  /// **'All day'**
  String get automationsWindowAllDay;

  /// No description provided for @automationsWindowCustom.
  ///
  /// In en, this message translates to:
  /// **'Custom'**
  String get automationsWindowCustom;

  /// No description provided for @automationsWindowFrom.
  ///
  /// In en, this message translates to:
  /// **'From'**
  String get automationsWindowFrom;

  /// No description provided for @automationsWindowInvalid.
  ///
  /// In en, this message translates to:
  /// **'The end time must be after the start time.'**
  String get automationsWindowInvalid;

  /// No description provided for @automationsWindowTo.
  ///
  /// In en, this message translates to:
  /// **'To'**
  String get automationsWindowTo;

  /// No description provided for @automationsTitle.
  ///
  /// In en, this message translates to:
  /// **'Automations'**
  String get automationsTitle;

  /// No description provided for @automationsTitlePlaceholder.
  ///
  /// In en, this message translates to:
  /// **'Automation title'**
  String get automationsTitlePlaceholder;

  /// No description provided for @automationsTitleRequired.
  ///
  /// In en, this message translates to:
  /// **'Title is required'**
  String get automationsTitleRequired;

  /// No description provided for @tabAgents.
  ///
  /// In en, this message translates to:
  /// **'Agents'**
  String get tabAgents;

  /// No description provided for @tabAutomations.
  ///
  /// In en, this message translates to:
  /// **'Automations'**
  String get tabAutomations;

  /// No description provided for @tabProfile.
  ///
  /// In en, this message translates to:
  /// **'Profile'**
  String get tabProfile;

  /// No description provided for @tabTasks.
  ///
  /// In en, this message translates to:
  /// **'Tasks'**
  String get tabTasks;

  /// No description provided for @searchHint.
  ///
  /// In en, this message translates to:
  /// **'Search sessions, tasks, automations'**
  String get searchHint;

  /// No description provided for @searchRecent.
  ///
  /// In en, this message translates to:
  /// **'Recent'**
  String get searchRecent;

  /// No description provided for @searchSessions.
  ///
  /// In en, this message translates to:
  /// **'Sessions'**
  String get searchSessions;

  /// No description provided for @searchNoResults.
  ///
  /// In en, this message translates to:
  /// **'No results found'**
  String get searchNoResults;

  /// No description provided for @searchPrompt.
  ///
  /// In en, this message translates to:
  /// **'Type to search sessions, tasks, and automations'**
  String get searchPrompt;

  /// No description provided for @searchFailed.
  ///
  /// In en, this message translates to:
  /// **'Search failed — check your connection and try again'**
  String get searchFailed;

  /// No description provided for @searchTimeout.
  ///
  /// In en, this message translates to:
  /// **'Search timed out — try a more specific query'**
  String get searchTimeout;

  /// No description provided for @searchSessionsOnly.
  ///
  /// In en, this message translates to:
  /// **'Showing sessions only'**
  String get searchSessionsOnly;

  /// No description provided for @gettingStartedTitle.
  ///
  /// In en, this message translates to:
  /// **'Get started'**
  String get gettingStartedTitle;

  /// No description provided for @gettingStartedProgress.
  ///
  /// In en, this message translates to:
  /// **'{done} of {total} done'**
  String gettingStartedProgress(int done, int total);

  /// No description provided for @gettingStartedConnectTitle.
  ///
  /// In en, this message translates to:
  /// **'Connect a computer'**
  String get gettingStartedConnectTitle;

  /// No description provided for @gettingStartedConnectHint.
  ///
  /// In en, this message translates to:
  /// **'Set up Vicoa on your desktop'**
  String get gettingStartedConnectHint;

  /// No description provided for @gettingStartedSessionTitle.
  ///
  /// In en, this message translates to:
  /// **'Start a session'**
  String get gettingStartedSessionTitle;

  /// No description provided for @gettingStartedSessionHint.
  ///
  /// In en, this message translates to:
  /// **'Spin up a coding agent'**
  String get gettingStartedSessionHint;

  /// No description provided for @gettingStartedMessageTitle.
  ///
  /// In en, this message translates to:
  /// **'Send a message'**
  String get gettingStartedMessageTitle;

  /// No description provided for @gettingStartedMessageHint.
  ///
  /// In en, this message translates to:
  /// **'Chat with your agent'**
  String get gettingStartedMessageHint;

  /// No description provided for @gettingStartedCollapse.
  ///
  /// In en, this message translates to:
  /// **'Collapse'**
  String get gettingStartedCollapse;

  /// No description provided for @gettingStartedDismiss.
  ///
  /// In en, this message translates to:
  /// **'Dismiss'**
  String get gettingStartedDismiss;

  /// No description provided for @gettingStartedConnectSheetTitle.
  ///
  /// In en, this message translates to:
  /// **'Set up Vicoa on your computer'**
  String get gettingStartedConnectSheetTitle;

  /// No description provided for @gettingStartedConnectSheetBody.
  ///
  /// In en, this message translates to:
  /// **'Vicoa runs your coding agents on your computer. Set it up on your desktop, then start, watch, and steer them from your phone.'**
  String get gettingStartedConnectSheetBody;

  /// No description provided for @gettingStartedEmailLinkCta.
  ///
  /// In en, this message translates to:
  /// **'Email me the setup link'**
  String get gettingStartedEmailLinkCta;

  /// No description provided for @gettingStartedEmailSentCta.
  ///
  /// In en, this message translates to:
  /// **'Setup link sent'**
  String get gettingStartedEmailSentCta;

  /// No description provided for @gettingStartedEmailSentToast.
  ///
  /// In en, this message translates to:
  /// **'We\'ve sent a get-started link to {target}.'**
  String gettingStartedEmailSentToast(Object target);

  /// No description provided for @gettingStartedDownloadCta.
  ///
  /// In en, this message translates to:
  /// **'Or open vicoa.ai/download'**
  String get gettingStartedDownloadCta;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'zh'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
    case 'zh':
      return AppLocalizationsZh();
  }

  throw FlutterError(
      'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
      'an issue with the localizations generation tool. Please file an issue '
      'on GitHub with a reproducible sample app and the gen-l10n configuration '
      'that was used.');
}
