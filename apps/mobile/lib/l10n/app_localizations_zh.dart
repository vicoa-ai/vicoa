// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Chinese (`zh`).
class AppLocalizationsZh extends AppLocalizations {
  AppLocalizationsZh([String locale = 'zh']) : super(locale);

  @override
  String get tasksAllProjects => '所有项目';

  @override
  String get tasksCancel => '取消';

  @override
  String get tasksCouldNotLoad => '无法加载待办';

  @override
  String get tasksCreate => '创建';

  @override
  String get tasksDelete => '删除';

  @override
  String get tasksDeleteConfirmBody => '该待办将被永久删除，此操作无法撤销。';

  @override
  String get tasksDeleteConfirmTitle => '删除待办？';

  @override
  String get tasksDescriptionFieldLabel => '描述';

  @override
  String get tasksDescriptionPlaceholder => '添加详情…';

  @override
  String get tasksEdit => '编辑';

  @override
  String get tasksEditTask => '编辑待办';

  @override
  String get tasksLabelsFieldLabel => '标签';

  @override
  String get tasksNewTask => '新建待办';

  @override
  String get tasksDisplay => '显示';

  @override
  String get tasksInbox => '收件箱';

  @override
  String get tasksLabelsButton => '标签';

  @override
  String get tasksPropPriority => '优先级';

  @override
  String get tasksPropProject => '项目';

  @override
  String get tasksPropStatus => '状态';

  @override
  String get tasksNoTasksSubtitle => '创建待办，规划你可以交给 AI 的工作。';

  @override
  String get tasksNoTasksTitle => '还没有待办';

  @override
  String get tasksPriorityFieldLabel => '优先级';

  @override
  String get tasksPriorityHigh => '高';

  @override
  String get tasksPriorityLow => '低';

  @override
  String get tasksPriorityMedium => '中';

  @override
  String get tasksPriorityNone => '无优先级';

  @override
  String get tasksPriorityUrgent => '紧急';

  @override
  String get tasksProjectFieldLabel => '项目';

  @override
  String get tasksPullToRefresh => '下拉刷新';

  @override
  String get tasksSave => '保存';

  @override
  String get tasksSaveFailed => '无法保存待办，请重试。';

  @override
  String get tasksStartSession => '开始任务';

  @override
  String get tasksSubtasks => '子任务';

  @override
  String get tasksStatusBacklog => '待规划';

  @override
  String get tasksStatusBlocked => '受阻';

  @override
  String get tasksStatusCancelled => '已取消';

  @override
  String get tasksStatusDone => '已完成';

  @override
  String get tasksStatusFieldLabel => '状态';

  @override
  String get tasksStatusInProgress => '进行中';

  @override
  String get tasksStatusInReview => '审核中';

  @override
  String get tasksStatusTodo => '待办';

  @override
  String get tasksTaskDeleted => '待办已删除';

  @override
  String get tasksTitle => '待办';

  @override
  String get tasksTitleFieldLabel => '标题';

  @override
  String get tasksTitlePlaceholder => '需要做什么？';

  @override
  String get tasksTitleRequired => '请输入标题';

  @override
  String get accountCautionZone => '危险操作区';

  @override
  String get accountDeleteAccount => '删除账号';

  @override
  String get accountDeleteDialogBody => '你的所有数据将被永久删除。确定要继续吗？';

  @override
  String get accountDeleteDialogTitle => '确认删除账号？';

  @override
  String get accountEmail => '邮箱';

  @override
  String get accountLogOut => '退出登录';

  @override
  String get accountName => '名称';

  @override
  String get accountNameHint => '访客';

  @override
  String get accountRegistration => '注册';

  @override
  String get accountTitle => '账号';

  @override
  String get addToChatChooseFiles => '文件';

  @override
  String get addToChatCommands => '工具';

  @override
  String get addToChatPhotoLibrary => '照片';

  @override
  String get addToChatSkillsOrCommands => '技能、工具';

  @override
  String get addToChatTakePhoto => '相机';

  @override
  String agentCatalogReasoningLabel(Object label) {
    return '推理 - $label';
  }

  @override
  String agentCatalogThinkingLabel(Object label) {
    return '思考 - $label';
  }

  @override
  String get agentChatAddToChat => '添加到对话';

  @override
  String get agentChatAgentMode => 'Agent 模式';

  @override
  String get agentChatCancelQueuedMessageTooltip => '取消消息';

  @override
  String get agentChatRevertQueuedMessageTooltip => '移回输入框编辑';

  @override
  String get agentChatCancelledLabel => '已取消';

  @override
  String get agentChatCloseFailed => '关闭任务失败，请重试。';

  @override
  String agentChatCopiedToClipboard(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '已复制 $count 条消息到剪贴板',
    );
    return '$_temp0';
  }

  @override
  String get agentChatCopyFailed => '复制消息失败';

  @override
  String get agentChatCopyResponse => '复制回复';

  @override
  String get agentChatDeleteFailed => '删除任务失败，请重试。';

  @override
  String get agentChatErrorLoadingMessages => '加载消息出错';

  @override
  String get agentChatInitFailed => '初始化对话失败';

  @override
  String get agentChatMentionFiles => '文件';

  @override
  String agentChatNewMessagesCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count 条消息',
    );
    return '$_temp0';
  }

  @override
  String get agentChatNoMessagesSelected => '未选择任何消息';

  @override
  String get agentChatNoMessagesToShare => '没有可分享的消息';

  @override
  String get agentChatPermissionMode => '权限模式';

  @override
  String get agentChatPinFailed => '无法置顶任务';

  @override
  String agentChatQueuedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count 条排队中',
    );
    return '$_temp0';
  }

  @override
  String get agentChatQueuedLabel => '排队中';

  @override
  String get agentChatQueuedSheetTitle => '排队消息';

  @override
  String get agentChatRenameFailed => '重命名任务失败，请重试。';

  @override
  String get agentChatSessionReady => '任务已就绪';

  @override
  String get agentChatSessionRenamed => '任务重命名成功';

  @override
  String get agentChatSessionTitle => '任务';

  @override
  String get agentChatShareFailed => '分享消息失败';

  @override
  String get agentChatShareResponse => '分享回复';

  @override
  String get agentChatShowSlashCommands => '显示斜杠命令';

  @override
  String get agentChatStartingYourSession => '正在启动任务';

  @override
  String get agentChatThinking => '思考';

  @override
  String get agentChatThinkingOff => '关闭';

  @override
  String get agentChatThinkingOn => '开启';

  @override
  String get agentChatTranscribing => '转写中…';

  @override
  String get agentChatUnexpectedError => '发生了意外错误';

  @override
  String get agentChatUnpinFailed => '无法取消置顶任务';

  @override
  String get agentChatWaitingForMessages => '等待消息中';

  @override
  String get agentConfigAgent => 'Agent';

  @override
  String agentConfigBetaLabel(Object label) {
    return '$label（Beta）';
  }

  @override
  String get agentConfigMode => '模式';

  @override
  String get agentConfigModel => '模型';

  @override
  String get agentConfigNotInstalled => '未安装';

  @override
  String agentConfigNotInstalledPrefix(Object label) {
    return '$label 未安装在这台机器上。请先安装，然后重启 ';
  }

  @override
  String get agentConfigNotInstalledSuffix => ' 以使用它。';

  @override
  String get agentConfigPanelAgent => 'Agent';

  @override
  String get agentConfigPanelMode => '模式';

  @override
  String get agentConfigPanelModel => '模型';

  @override
  String get agentConfigPanelPermission => '权限';

  @override
  String get agentConfigPanelReasoning => '推理';

  @override
  String get agentConfigPanelThinking => '思考';

  @override
  String get agentConfigPanelUnknownAgent => '未知 Agent — 请更新应用以进行配置。';

  @override
  String get agentConfigPermission => '权限';

  @override
  String get agentConfigReasoningEffort => '推理强度';

  @override
  String get agentConfigThinkingEffort => '思考强度';

  @override
  String get agentConfigUnknownAgent => '未知 Agent —— 请更新 App 以进行配置。';

  @override
  String get appLanguageTitle => '语言';

  @override
  String get appearanceChat => '聊天';

  @override
  String get appearanceCodeBlock => '代码块';

  @override
  String get appearanceCollapseLongCode => '折叠长代码';

  @override
  String get appearanceCollapseToolCalls => '折叠工具调用';

  @override
  String get appearanceDarkMode => '深色模式';

  @override
  String get appearanceLanguage => '语言';

  @override
  String get appearanceLinesBeforeCollapsing => '折叠前 代码行数';

  @override
  String get appearanceShowFilter => '显示筛选';

  @override
  String get appearanceShowLivePreview => '显示实时预览';

  @override
  String get appearanceTitle => '外观';

  @override
  String get askUserQuestionPanelCancelling => '取消中…';

  @override
  String askUserQuestionPanelQuestionNumber(Object number) {
    return '问题 $number';
  }

  @override
  String get askUserQuestionPanelSubmit => '提交';

  @override
  String get askUserQuestionPanelSubmitting => '提交中…';

  @override
  String get askUserQuestionPanelTypeSomething => '输入内容';

  @override
  String get askUserQuestionPanelTypeYourAnswer => '输入你的回答';

  @override
  String get authEmailChangeConfirmationSent => '更改邮箱的确认邮件已发送';

  @override
  String get authOptionsAndConnector => ' 和 ';

  @override
  String get authOptionsContinueWithApple => '使用 Apple 继续';

  @override
  String get authOptionsContinueWithEmail => '使用邮箱继续';

  @override
  String get authOptionsContinueWithGoogle => '使用 Google 继续';

  @override
  String get authOptionsLegalPrefix => '继续即表示你同意\n';

  @override
  String get authOptionsPrivacyPolicy => '隐私政策';

  @override
  String get authOptionsSubtitle => '在手机上拥有一个AI编程和助手团队';

  @override
  String get authOptionsTermsOfUse => '使用条款';

  @override
  String get authOptionsTitle => '开始使用吧';

  @override
  String get billingXNoOffering => '暂无可用的订阅方案';

  @override
  String billingXPaywallLoadError(Object error) {
    return '加载订阅页面出错：$error';
  }

  @override
  String get chatErrorLoadMessagesFailed => '加载消息失败，请检查网络连接。';

  @override
  String get chatInputAddToChat => '添加到聊天';

  @override
  String get chatInputBrowseFiles => '浏览文件';

  @override
  String get chatInputCliOutdated => 'Vicoa CLI 可能已过期。请升级后访问文件和更改。';

  @override
  String get chatInputModelConfig => '设置';

  @override
  String get chatInputOpenWebPreview => '打开网页预览';

  @override
  String get chatInputPlaceholder => '发消息、@文件、/技能或命令';

  @override
  String get chatInputSessionConfig => '设置';

  @override
  String get chatInputSessionEnded => '任务已结束，聊天已关闭';

  @override
  String get chatInputSessionReadOnly => '任务已关闭，配置为只读。';

  @override
  String get chatInputStopTask => '停止当前任务';

  @override
  String get chatOptionsInfo => '信息';

  @override
  String get chatOptionsPin => '置顶';

  @override
  String get chatOptionsRename => '重命名';

  @override
  String get chatOptionsUnpin => '取消置顶';

  @override
  String get commonBack => '返回';

  @override
  String get commonCancel => '取消';

  @override
  String get commonClose => '关闭';

  @override
  String get commonConfirm => '确认';

  @override
  String get commonContinue => '继续';

  @override
  String get commonCopied => '已复制';

  @override
  String get commonCopy => '复制';

  @override
  String get commonDelete => '删除';

  @override
  String get commonDone => '完成';

  @override
  String get commonEdit => '编辑';

  @override
  String get commonError => '错误';

  @override
  String get commonLoading => '加载中…';

  @override
  String get commonNext => '下一步';

  @override
  String get commonNo => '否';

  @override
  String get commonOk => '好';

  @override
  String get commonRemove => '移除';

  @override
  String get commonRetry => '重试';

  @override
  String get commonSave => '保存';

  @override
  String get commonSearch => '搜索';

  @override
  String get commonSettings => '设置';

  @override
  String get commonShare => '分享';

  @override
  String get commonSignIn => '登录';

  @override
  String get commonSignOut => '退出登录';

  @override
  String get commonSignUp => '注册';

  @override
  String get commonSkip => '跳过';

  @override
  String get commonYes => '是';

  @override
  String get configureSetupConfiguringBest => '你的 AI 助手\n即将就绪';

  @override
  String get configureSetupJustAMoment => '请稍候……';

  @override
  String get configureSetupSocialProof => '使用 Vicoa 的人随时随地借助\nAI 编程助手，开发得更快。';

  @override
  String get confirmDialogAreYouSure => '确定要继续吗？';

  @override
  String get confirmRatingBody => '感谢你的支持！\n\n如果你已经给了我们五星好评，点击下方按钮领取免费消息额度。';

  @override
  String get confirmRatingDoneButton => '我已完成';

  @override
  String get confirmRatingGiftButton => '继续使用';

  @override
  String get confirmRatingGiftText => '太棒了！你获得了 50 条免费消息！';

  @override
  String get confirmRatingTitle => '给我们打个五星好评吧！';

  @override
  String get connectComputerLinkCopied => '链接已复制';

  @override
  String get connectComputerLoginSameAccount => '下载桌面应用并用同一个账号登录，你的电脑会自动连接。';

  @override
  String get connectComputerTitle => '连接你的电脑';

  @override
  String get connectComputerViewDocs => '查看完整文档';

  @override
  String get credtiHistoryTitle => '使用记录';

  @override
  String get dateRangeXApply => '应用';

  @override
  String get dateRangeXEndDate => '结束日期';

  @override
  String get dateRangeXStartDate => '开始日期';

  @override
  String get dateRangeXTitle => '自定义日期范围';

  @override
  String get dateRangeXWeekdayFri => '五';

  @override
  String get dateRangeXWeekdayMon => '一';

  @override
  String get dateRangeXWeekdaySat => '六';

  @override
  String get dateRangeXWeekdaySun => '日';

  @override
  String get dateRangeXWeekdayThu => '四';

  @override
  String get dateRangeXWeekdayTue => '二';

  @override
  String get dateRangeXWeekdayWed => '三';

  @override
  String get dateToday => '今天';

  @override
  String get dateYesterday => '昨天';

  @override
  String get directoryPickerRecent => '最近';

  @override
  String get directoryPickerWorkingDirectory => '工作目录';

  @override
  String get errorStateDisplaySignInAgain => '重新登录';

  @override
  String get errorStateDisplayTryAgain => '重试';

  @override
  String get errorStateDisplayUnexpectedError => '发生了意外错误';

  @override
  String get fileViewerXAddToContext => '添加到上下文';

  @override
  String fileViewerXBinaryFile(Object size) {
    return '二进制文件（$size）';
  }

  @override
  String get fileViewerXDetailNotDownloaded => '文件未下载';

  @override
  String get fileViewerXDetailOutdated => '文件可能已过时';

  @override
  String fileViewerXErrDefault(Object code) {
    return '无法加载此文件（$code）。';
  }

  @override
  String get fileViewerXErrMachineOffline => '机器已离线。';

  @override
  String get fileViewerXErrNoHandler => '请更新此机器上的 daemon — 旧版本不支持文件查看。';

  @override
  String get fileViewerXErrNotAFile => '不是文件。';

  @override
  String get fileViewerXErrOutsideProject => '路径在项目之外。';

  @override
  String get fileViewerXErrPathNotFound => '该文件已不存在。';

  @override
  String get fileViewerXErrPermissionDenied => '权限被拒绝。';

  @override
  String get fileViewerXErrTimeout => '机器响应超时。';

  @override
  String get fileViewerXFileNotDownloaded => '此设备上未下载该文件。';

  @override
  String get fileViewerXImageTooLarge => '图片过大，无法在移动端预览。';

  @override
  String get fileViewerXPreviewNotAvailable => '无法预览。';

  @override
  String get fileViewerXReconnectToView => '重新连接机器以查看。';

  @override
  String get fileViewerXRefresh => '刷新';

  @override
  String fileViewerXShowingFirstPortion(Object size) {
    return '仅显示 $size 的开头部分。在桌面端查看剩余内容。';
  }

  @override
  String filesGitXBinaryFileChanged(Object size) {
    return '二进制文件已更改 · $size';
  }

  @override
  String get filesGitXCollapseAllTooltip => '全部折叠';

  @override
  String filesGitXCouldntLoadDiff(Object code) {
    return '无法加载 diff — $code';
  }

  @override
  String get filesGitXCouldntLoadStatus => '无法加载状态';

  @override
  String filesGitXDetachedAt(Object branch) {
    return '（分离于 $branch）';
  }

  @override
  String get filesGitXDiffTruncated => 'Diff 已截断 — 在桌面端查看剩余内容。';

  @override
  String get filesGitXExpandAllTooltip => '全部展开';

  @override
  String get filesGitXHideWhitespaceTooltip => '隐藏空白字符';

  @override
  String get filesGitXNoChangesVsHead => '与 HEAD 相比没有更改。';

  @override
  String get filesGitXNoUpstream => '  ·  无上游分支';

  @override
  String get filesGitXNotARepoSubtitle => '在 Git 项目中打开此目录以查看更改。';

  @override
  String get filesGitXNotARepoTitle => '不是 Git 仓库';

  @override
  String get filesGitXReconnectToSeeChanges => '重新连接机器以查看更改。';

  @override
  String get filesGitXRefreshTooltip => '刷新';

  @override
  String filesGitXSectionLabel(Object label, Object count) {
    return '$label · $count';
  }

  @override
  String get filesGitXSectionStaged => '已暂存';

  @override
  String get filesGitXSectionUnstaged => '未暂存';

  @override
  String get filesGitXSectionUntracked => '未跟踪';

  @override
  String filesGitXShowMoreLines(int count) {
    return '再显示 $count 行';
  }

  @override
  String get filesGitXShowWhitespaceTooltip => '显示空白字符';

  @override
  String get filesGitXStatusNotLoaded => '此设备上未加载 Git 状态。';

  @override
  String get filesGitXWordWrapTooltip => '自动换行';

  @override
  String get filesGitXWorkingTreeClean => '工作区干净';

  @override
  String get filesScreenTabChanges => '改动';

  @override
  String get filesScreenTabFiles => '文件';

  @override
  String filesXErrDefault(Object code) {
    return '无法列出此目录（$code）。';
  }

  @override
  String get filesXErrNoHandler => '请更新此机器上的 daemon — 旧版本不支持文件列表。';

  @override
  String get filesXErrNotADirectory => '项目路径不是目录。';

  @override
  String get filesXErrOutsideProject => '路径在项目根目录之外。';

  @override
  String get filesXErrPathNotFound => '在机器上未找到项目目录。';

  @override
  String get filesXErrPermissionDenied => '无权读取此目录。';

  @override
  String get filesXErrTimeout => '机器响应超时。';

  @override
  String filesXMachineOffline(Object detail) {
    return '机器离线，$detail。';
  }

  @override
  String get filesXNoFiles => '没有文件';

  @override
  String get filesXNotLoaded => '此设备上未加载文件。';

  @override
  String get filesXOfflineDetailDefault => '文件可能已过时';

  @override
  String filesXProjectLabel(Object cwd) {
    return '项目：$cwd';
  }

  @override
  String get filesXReconnectToBrowse => '重新连接机器以浏览文件。';

  @override
  String get filterAgentType => 'Agent 类型';

  @override
  String get filterAgentTypeHeader => 'Agent 类型';

  @override
  String get filterAll => '全部';

  @override
  String get filterAllTime => '全部时间';

  @override
  String get filterClosed => '已关闭';

  @override
  String get filterCustomRange => '自定义范围';

  @override
  String get filterDate => '日期';

  @override
  String get filterDateRange => '日期范围';

  @override
  String get filterDateRangeHeader => '日期范围';

  @override
  String get filterFilter => '筛选';

  @override
  String get filterGroupBy => '分组方式';

  @override
  String get filterInProgress => '进行中';

  @override
  String get filterInReview => '待审查';

  @override
  String get filterLast7Days => '最近 7 天';

  @override
  String get filterNotClosed => '未关闭';

  @override
  String get filterProject => '项目';

  @override
  String get filterStatus => '状态';

  @override
  String get filterStatusHeader => '状态';

  @override
  String get filterTime => '时间';

  @override
  String get filterType => '类型';

  @override
  String get giftDialogFreeCredits => '太棒了！你获得了 5 个免费额度！';

  @override
  String get helpFeedbackBlog => '博客';

  @override
  String get helpFeedbackChangelog => '更新日志';

  @override
  String get helpFeedbackContactUs => '联系我们';

  @override
  String get helpFeedbackDocumentation => '文档';

  @override
  String get helpFeedbackFeatureRequest => '功能建议与问题反馈';

  @override
  String get helpFeedbackFeedback => '反馈';

  @override
  String get helpFeedbackTitle => '帮助与反馈';

  @override
  String get homeCloseFailed => '关闭任务失败，请重试。';

  @override
  String get homeDeleteFailed => '删除任务失败，请重试。';

  @override
  String get homeErrorConnecting => '正在连接服务器...如长时间无法连接，请前往账户页面重新登录。';

  @override
  String get homeErrorLoadSessionsFailed => '加载任务失败，请重试。';

  @override
  String get homeErrorOffline => '无网络连接，请检查网络。';

  @override
  String get homeErrorOfflineCached => '无网络连接，显示缓存数据。';

  @override
  String get homeErrorServiceUnavailable => '暂时无法连接到服务。';

  @override
  String get homeErrorServiceUnavailableRetry => '暂时无法连接到服务，请稍后重试。';

  @override
  String get homeErrorSessionExpired => '登录已过期，请重新登录。';

  @override
  String get homeGroupNoProject => '未分配项目';

  @override
  String get homeGroupPinned => '置顶';

  @override
  String get homePinFailed => '无法置顶任务';

  @override
  String get homeRenameFailed => '重命名任务失败，请重试。';

  @override
  String get homeSessionClosed => '任务已关闭';

  @override
  String get homeSessionDeleted => '任务删除成功';

  @override
  String get homeSessionRenamed => '任务重命名成功';

  @override
  String get homeUnpinFailed => '无法取消置顶任务';

  @override
  String impactHeadline(Object phrase) {
    return '把 AI 助手带在身边';
  }

  @override
  String get impactWithRatingHeadline => '把 AI 助手带在身边';

  @override
  String get impactWithRatingNameMarcus => '张伟';

  @override
  String get impactWithRatingNameSarah => '李娜';

  @override
  String get impactWithRatingNameTom => '王磊';

  @override
  String get impactWithRatingTestimonialMarcus =>
      '太喜欢这个 App 了！改变了我的工作方式。以前一定要在电脑边，现在手机上就能控制 AI 干活。';

  @override
  String get impactWithRatingTestimonialSarah =>
      '终于！在手机上用上 Claude Code 等模型。在上下班、出门路上，都能随时给 AI 布置任务。';

  @override
  String get impactWithRatingTestimonialTom =>
      '很实用、很喜欢。就像贴身秘书，远程操控 AI 做事，还能和 Obsidian 联动，太爽了！';

  @override
  String get infoDialogAreYouSure => '确定要继续吗？';

  @override
  String get introLandingPage1Item1 => '随时随地发送指令';

  @override
  String get introLandingPage1Item2 => '即时获得 AI 回复';

  @override
  String get introLandingPage1Item3 => '在所有设备间同步';

  @override
  String get introLandingPage1Subtitle => '直接从手机向运行在电脑上的 AI 代理发送指令。';

  @override
  String get introLandingPage1Title => '在手机上\n远程驱动 AI 编程';

  @override
  String get introLandingPage2Item1 => '任务完成即时提醒';

  @override
  String get introLandingPage2Item2 => '在手机上一键审批';

  @override
  String get introLandingPage2Item3 => '随时随地与代理对话';

  @override
  String get introLandingPage2Subtitle => '代理需要输入时即时提醒，无需碰电脑即可持续推进。';

  @override
  String get introLandingPage2Title => '代理在干活，\n你随时收到通知。';

  @override
  String get introLandingPage3Item1 => '支持 Claude Code、Codex 和 OpenCode';

  @override
  String get introLandingPage3Item2 => '所有代理任务集中管理';

  @override
  String get introLandingPage3Item3 => '浏览历史对话';

  @override
  String get introLandingPage3Subtitle => '在一处监控所有项目的代理、浏览历史记录等。';

  @override
  String get introLandingPage3Title => '一个界面，\n管理所有代理';

  @override
  String get introLandingPage4Item1 => '下载桌面应用';

  @override
  String get introLandingPage4Item2 => '使用同一账号登录';

  @override
  String get introLandingPage4Item3 => '立即配对成功！开始编程吧。';

  @override
  String get introLandingPage4Subtitle => '点几下，就能直接在手机上管理桌面端项目。';

  @override
  String get introLandingPage4Title => '数秒即可连接';

  @override
  String get landingHeadline => '手机远程控制 AI\n在电脑上完成任务';

  @override
  String get landingSubtitle => '随时随地，让多个AI助手为你工作';

  @override
  String get landingSupports => '支持';

  @override
  String get languageAutomatic => '自动';

  @override
  String get languageChinese => '中文';

  @override
  String get languageEnglish => 'English';

  @override
  String get languageFollowSystem => '跟随系统';

  @override
  String get machineActionsRemoveContent =>
      '确定要移除此机器吗？在再次运行 Vicoa CLI 之前，你将无法从它启动新任务。';

  @override
  String get machineActionsRemoveTitle => '移除机器';

  @override
  String get machineActionsRemoving => '正在移除机器…';

  @override
  String get machineActionsRenamePlaceholder => '输入机器名称…';

  @override
  String get machineActionsRenameTitle => '重命名机器';

  @override
  String get machineActionsRenaming => '正在重命名机器…';

  @override
  String get machineDetailAgentNotFound => '未找到';

  @override
  String get machineDetailAgents => 'Agents';

  @override
  String get machineDetailCautionZone => '危险操作区';

  @override
  String get machineDetailCouldNotLoad => '无法加载机器';

  @override
  String get machineDetailHomeDirectory => '主目录';

  @override
  String get machineDetailHostname => '主机名';

  @override
  String get machineDetailInstalled => '已安装';

  @override
  String get machineDetailLastHeartbeat => '最近心跳';

  @override
  String get machineDetailMachine => '机器';

  @override
  String get machineDetailNotFound => '未找到机器';

  @override
  String get machineDetailOffline => '离线';

  @override
  String get machineDetailOnline => '在线';

  @override
  String get machineDetailPlatform => '平台';

  @override
  String get machineDetailRemoveDescription =>
      '从你的账号中移除此机器。任务历史会被保留，但你将无法在此机器上开始新的任务。';

  @override
  String get machineDetailRemoveMachine => '移除机器';

  @override
  String get machineDetailRunPrefix => '运行 ';

  @override
  String get machineDetailRunSuffix => ' 即可让它上线';

  @override
  String get machineDetailStatus => '状态';

  @override
  String get machineDetailSystem => '系统';

  @override
  String get machineDetailUnknown => '未知';

  @override
  String get machineDetailVicoaCli => 'Vicoa CLI';

  @override
  String get machinesCouldNotLoad => '无法加载机器';

  @override
  String get machinesMachineRemoved => '机器已移除';

  @override
  String get machinesNoMachinesSubtitle =>
      '在电脑上运行 Vicoa CLI 即可连接，然后即可随时随地开始远程任务。';

  @override
  String get machinesNoMachinesYet => '暂无机器';

  @override
  String get machinesPullToRefresh => '下拉刷新以重试。';

  @override
  String get machinesTitle => '机器';

  @override
  String markdownXMoreLines(Object count) {
    return '还有 $count 行';
  }

  @override
  String messageSelectionSheetCount(Object selected, Object total) {
    return '已选择 $selected/$total';
  }

  @override
  String get messageSelectionSheetDeselectAll => '取消全选';

  @override
  String get messageSelectionSheetSelectAll => '全选';

  @override
  String get messageSelectionSheetTitle => '选择消息';

  @override
  String get messageSelectionSheetYou => '你';

  @override
  String get newSessionAddToChat => '添加到对话';

  @override
  String get newSessionAgent => 'Agent';

  @override
  String newSessionAgentDidNotStart(Object label) {
    return '$label 未能在这台机器上启动。\n\n请确认它已安装，并且你的 Vicoa daemon 已更新到最新版本，然后重试。';
  }

  @override
  String get newSessionCurrentBranch => '当前分支';

  @override
  String get newSessionLoadingMachines => '正在加载机器…';

  @override
  String get newSessionMachine => '机器';

  @override
  String get newSessionNewSession => '新任务';

  @override
  String get newSessionNewWorktree => '新建工作树';

  @override
  String get newSessionOffline => '（离线）';

  @override
  String get newSessionRunPrefix => '运行 ';

  @override
  String get newSessionSelectMachine => '选择一台机器';

  @override
  String get newSessionStartedNoStatus => '任务已启动，但无法确定状态。';

  @override
  String get newSessionTheAgent => '该 Agent';

  @override
  String get newSessionToBringOnline => ' 让你的机器上线。';

  @override
  String get newSessionUnableToStart => '无法启动任务';

  @override
  String get newSessionUnableToStartBody =>
      '可能的原因：\n\n• 机器无响应\n• 网络连接问题\n• 目录路径无效\n\n请检查机器状态后重试。';

  @override
  String get newSessionWorkingDirectory => '工作目录';

  @override
  String get newSessionWorktree => '工作树';

  @override
  String get newsAndConnector => '，然后';

  @override
  String get newsBadNewsPrefix => '坏消息是\n';

  @override
  String get newsCodeFromPhone => '让 AI 继续工作。';

  @override
  String get newsCodingNext12Months => '\n在 AI 编程上。';

  @override
  String get newsGetNotified => '接收通知';

  @override
  String get newsGreatNewsPrefix => '好消息是 \n';

  @override
  String get newsJustWaiting => '只是在等待 AI 的完成任务';

  @override
  String get newsMinutesUnit => ' 分钟 ';

  @override
  String get newsTransitHeadline => '有坏消息\n也有好消息';

  @override
  String get newsVicoaFreesYouUp => 'Vicoa 让你更加自由，你可以在手机上';

  @override
  String newsWastedMinutes(Object minutes) {
    return '$minutes+ 分钟 ';
  }

  @override
  String get newsYouWillSpend => '未来12个月，你将花费 ';

  @override
  String get newsYouWillWaste => '你将浪费 ';

  @override
  String get noCreditSheetGetMoreFreeMessages => '获取更多免费消息';

  @override
  String get noCreditSheetGetMoreOrUnlock => '获取更多免费消息，或开通 Vicoa Pro 会员解锁无限消息';

  @override
  String get noCreditSheetInsufficientCredits => '额度不足';

  @override
  String get noCreditSheetUpgradeToPro => '开通 Vicoa Pro';

  @override
  String get noCreditSheetUsedAllMessages => '你已用完所有免费消息。';

  @override
  String get notificationAllSet => '全部设置完成！';

  @override
  String get notificationDontMissOut => 'AI 助手完成任务或需要你时，\n第一时间通知你。\n';

  @override
  String get notificationEnableButton => '开启通知';

  @override
  String get notificationInOnboardBody => 'AI 助手完成任务或需要你时，\n第一时间通知你。\n';

  @override
  String get notificationInOnboardEnable => '开启通知';

  @override
  String get notificationInOnboardMaybeLater => '以后再说';

  @override
  String get notificationInOnboardTitle => '开启通知？';

  @override
  String get notificationTitle => '通知';

  @override
  String get notificationTurnOnPrompt => '开启通知？';

  @override
  String get onboardGetNotifiedInstantly => '即时通知';

  @override
  String get onboardGetStarted => '开始使用';

  @override
  String get onboardNoMoreIdleWaiting => '告别等待';

  @override
  String get onboardPickUpWhereLeftOff => '随时接管';

  @override
  String get onboardSlide1Body => '创建一个任务后，AI 会持续执行，你可以专注于更重要的事情。';

  @override
  String get onboardSlide2Body => '把 AI 助手带在身边，无论身在何处，都能随时继续推进工作。';

  @override
  String get onboardSlide3Body => '当任务完成或需要你的决策时，AI 会第一时间通知你。';

  @override
  String get personalizingConfiguringBest => '正在为你准备最佳体验';

  @override
  String get personalizingHeadline => '你的 AI 助手\n即将就绪';

  @override
  String get personalizingSettingUp => '你的 AI 助手\n即将就绪';

  @override
  String get personalizingSocialProof => '数万名用户正在使用 Vicoa，\n让 AI 持续工作，完成更多任务。';

  @override
  String get proBenefitsPrioritySupportDesc => '需要帮助时，更快提供帮助和支持。';

  @override
  String get proBenefitsPrioritySupportTitle => '优先响应、专属支持';

  @override
  String get proBenefitsSubtitle => '你正享有全部高级功能：';

  @override
  String get proBenefitsSyncDesc => '手机、电脑、服务器随时切换，你的所有设备无缝同步进度。';

  @override
  String get proBenefitsSyncTitle => '无限跨设备使用';

  @override
  String get proBenefitsTitle => 'Vicoa Pro 会员权益';

  @override
  String get proBenefitsUnlimitedMessagesDesc => '随时随地向 AI 编程助手发送消息，不受次数限制。';

  @override
  String get proBenefitsUnlimitedMessagesTitle => '无限消息';

  @override
  String get proBenefitsVoiceInputDesc => '用语音直接给 AI 编程助手指令。';

  @override
  String get proBenefitsVoiceInputTitle => '语音输入';

  @override
  String get profileAccount => '账号';

  @override
  String get profileAppearance => '外观';

  @override
  String get profileFreeMessages => '免费消息';

  @override
  String get profileHelpFeedback => '帮助与反馈';

  @override
  String get profileInviteFriends => '邀请好友，赢取奖励';

  @override
  String get profileJoinDiscord => '加入 Discord';

  @override
  String get profileJoinPro => '成为 Vicoa Pro 会员';

  @override
  String get profileMachines => '机器';

  @override
  String get profileNotifications => '通知';

  @override
  String get profileProMember => 'Vicoa Pro 会员';

  @override
  String get profileProSubtitle => '无限任务、消息、和设备';

  @override
  String get profileReportIssue => '反馈问题';

  @override
  String get profileSubscription => '订阅';

  @override
  String get profileTitle => '我的';

  @override
  String get profileTutorials => '教程';

  @override
  String get profileVoiceAssistance => '语音助手';

  @override
  String get ratingDevelopersLike => '超过 100 名开发者喜欢 Vicoa';

  @override
  String get ratingLetsGetStarted => '开始吧';

  @override
  String get ratingMadeForYou => 'Vicoa 正是\n为你这样的人打造';

  @override
  String get ratingTestimonialMarcus =>
      'Vicoa 改变了我的工作方式。随时随地用上 OpenCode，让我再也不会错过交付的机会。';

  @override
  String get ratingTestimonialSarah =>
      '终于！在手机上用上 Claude Code。我可以在通勤时编程，随时修复 bug。';

  @override
  String get ratingTestimonialTom => '对于随时移动办公的开发者来说太完美了。在手机上调试、重构、开发新功能——太棒了！';

  @override
  String get ratingTitle => '给我们评分吧';

  @override
  String get realtimeStatusBannerReconnecting => '正在重新连接……';

  @override
  String get referFriendsAdditionalRewards => '额外奖励';

  @override
  String get referFriendsCodeUnavailableBody =>
      '我们暂时无法生成你的邀请码。请稍后重试，或联系我们寻求帮助。';

  @override
  String get referFriendsCodeUnavailableTitle => '邀请码暂不可用';

  @override
  String get referFriendsComeBackToClaim => '好友使用你的邀请码后，回到这里即可领取免费消息。';

  @override
  String get referFriendsContinueToUse => '继续使用';

  @override
  String get referFriendsCopiedToClipboard => '已复制到剪贴板';

  @override
  String get referFriendsEmailUs => '邮件联系我们';

  @override
  String referFriendsGotRewardMessages(Object count) {
    return '太棒了！你因邀请好友获得了 $count 条免费消息！';
  }

  @override
  String get referFriendsGrabYourCode => '获取你的邀请码';

  @override
  String referFriendsInvitedCount(Object count) {
    return '已邀请 $count 人';
  }

  @override
  String get referFriendsOnlyRegisteredUsers => '只有注册用户才能邀请好友。';

  @override
  String referFriendsShareMessage(Object code) {
    return '嘿，你听说过 Vicoa 吗？用这个 app，我可以在手机上随时随地运行 Claude Code、Codex 或 OpenCode。使用我的邀请码 $code 注册即可获得 50 条免费消息。从这里下载 app：https://apps.apple.com/app/id6751626168';
  }

  @override
  String get referFriendsShareSubject => 'Vicoa：随时随地用 AI 写代码';

  @override
  String get referFriendsShareYourCode => '分享你的邀请码';

  @override
  String get referFriendsSignUpNow => '立即注册';

  @override
  String get referFriendsSignupReward => '✅ 使用你的邀请码注册即可获得 50 条免费消息。';

  @override
  String get referFriendsTheyGet => '他们获得';

  @override
  String referFriendsTierBenefit(Object count, Object reward) {
    return '$count 位好友 → $reward 条免费消息';
  }

  @override
  String get referFriendsTitle => '邀请好友，赢取奖励';

  @override
  String get referFriendsYouGet => '你获得';

  @override
  String get rpcErrorComputerOffline => '你的电脑当前未连接。请确认 Vicoa 正在该电脑上运行，然后重试。';

  @override
  String get rpcErrorTimeout => '你的电脑响应超时。请确认 Vicoa 正在该电脑上运行，然后重试。';

  @override
  String get referralCodeHint => '邀请码（可选）';

  @override
  String get referralCodeThisIsOptional => '此项为可选';

  @override
  String get referralCodeTitle => '你有\n邀请码吗？';

  @override
  String relativeTimeHours(int count) {
    return '$count小时';
  }

  @override
  String relativeTimeMinutes(int count) {
    return '$count分钟';
  }

  @override
  String get relativeTimeNow => '刚刚';

  @override
  String relativeTimeSeconds(int count) {
    return '$count秒';
  }

  @override
  String get renameDialogEnterSessionName => '输入任务名称…';

  @override
  String get renameDialogRenameSession => '重命名任务';

  @override
  String get reportIssueDialogFailure => '发送失败，请重试。';

  @override
  String get reportIssueDialogHint => '描述你遇到的问题……';

  @override
  String get reportIssueDialogSending => '发送中……';

  @override
  String get reportIssueDialogSubmit => '提交';

  @override
  String get reportIssueDialogSuccess => '已发送，谢谢！';

  @override
  String reviewDialogCharCount(Object current, Object max) {
    return '$current / $max';
  }

  @override
  String get reviewDialogCouldBeBetter => '🤔 还能更好';

  @override
  String get reviewDialogEnjoyingDescription =>
      '我们很想知道你是否喜欢 Vicoa。你的反馈能帮助我们做得更好！';

  @override
  String get reviewDialogEnjoyingVicoa => '喜欢 Vicoa 吗？';

  @override
  String get reviewDialogIssueHint => '问题是……';

  @override
  String get reviewDialogLoveIt => '😍 很喜欢！';

  @override
  String get reviewDialogNeedsWorkDescription => '有什么不太对劲？告诉我们，我们会努力为你改进。';

  @override
  String get reviewDialogRateOnAppStore => '在 App Store 评分';

  @override
  String get reviewDialogReviewDescription =>
      '你的评价能帮助更多人了解 Vicoa，也能激励我们把它做得更好！';

  @override
  String get reviewDialogReviewVicoa => '给 Vicoa 评价 :)';

  @override
  String get reviewDialogSendFailed => '发送失败，请重试。';

  @override
  String get reviewDialogSendFeedback => '发送反馈';

  @override
  String get reviewDialogSending => '发送中……';

  @override
  String get reviewDialogThankYou => '感谢你的反馈！';

  @override
  String get reviewDialogWhatCouldBeBetter => '哪里可以改进？';

  @override
  String get sessionActionsArchive => '关闭';

  @override
  String get chatOptionsResume => '继续会话';

  @override
  String get sessionResumeOffline => '你的电脑已离线。重新上线后才能继续。';

  @override
  String get sessionResumeFailed => '继续会话失败';

  @override
  String get sessionActionsCloseContent => '确定要关闭此任务吗？';

  @override
  String get sessionActionsCloseTitle => '关闭任务';

  @override
  String get sessionActionsClosing => '正在关闭任务…';

  @override
  String get sessionActionsDeleteContent => '确定要删除此任务吗？此操作无法撤销。';

  @override
  String get sessionActionsDeleteTitle => '删除任务';

  @override
  String get sessionActionsDeleting => '正在删除任务…';

  @override
  String get sessionActionsRenamePlaceholder => '输入任务名称…';

  @override
  String get sessionActionsRenameTitle => '重命名任务';

  @override
  String get sessionActionsRenaming => '正在重命名任务…';

  @override
  String get sessionInfoAgent => 'Agent';

  @override
  String get sessionInfoAiAgent => 'AI Agent';

  @override
  String get sessionInfoCopyId => '复制 ID';

  @override
  String get sessionInfoCreated => '创建时间';

  @override
  String sessionInfoDateAtTime(Object date, Object time) {
    return '$date $time';
  }

  @override
  String get sessionInfoEditTitle => '编辑标题';

  @override
  String get sessionInfoId => 'ID';

  @override
  String get sessionInfoIdCopied => '任务 ID 已复制到剪贴板';

  @override
  String get sessionInfoLastUpdated => '最后更新';

  @override
  String get sessionInfoMachine => '机器';

  @override
  String get sessionInfoNameThisSession => '为此任务命名';

  @override
  String get sessionInfoProject => '项目';

  @override
  String get sessionInfoRenameFailed => '重命名任务失败';

  @override
  String get sessionInfoRenamed => '任务已重命名';

  @override
  String get sessionInfoSessionInfo => '任务信息';

  @override
  String get sessionInfoSessionName => '任务名称';

  @override
  String get sessionInfoSourceApp => 'App';

  @override
  String get sessionInfoSourceTerminal => '终端';

  @override
  String get sessionInfoStartedFrom => '启动';

  @override
  String get sessionInfoViewMachine => '查看机器';

  @override
  String get sessionInfoWorktree => '工作树';

  @override
  String get sessionListClosed => '任务已关闭';

  @override
  String get sessionListDeleted => '任务已删除';

  @override
  String get setupReminderNotificationBody =>
      '在电脑上下载 Vicoa 桌面应用并登录，随时随地使用 Claude Code、Codex 和 OpenCode。';

  @override
  String get setupReminderNotificationTitle => '把编程代理带到你的手机上 🚀';

  @override
  String get shareOptionsSheetCopiedToClipboard => '内容已复制到剪贴板';

  @override
  String get shareOptionsSheetCopyToClipboard => '复制到剪贴板';

  @override
  String get shareOptionsSheetShareAs => '分享为';

  @override
  String get shareOptionsSheetShareAsFile => '以文件分享';

  @override
  String get shareOptionsSheetShareAsText => '以文本分享';

  @override
  String get signInDialogBody => '请登录以使用此功能。';

  @override
  String get signInDialogLater => '稍后再说';

  @override
  String get signInDialogTitle => '登录以继续';

  @override
  String get signUpAlreadyHaveAccount => '已有账号？';

  @override
  String get signUpCreateAccount => '创建账号';

  @override
  String get signUpDontHaveAccount => '还没有账号？';

  @override
  String get signUpEmailLabel => '电子邮箱';

  @override
  String get signUpHaveReferralCode => '我有推荐码';

  @override
  String get signUpPasswordLabel => '密码';

  @override
  String get signUpPasswordsMismatch => '两次输入的密码不一致！';

  @override
  String get signUpReferralCodeLabel => '推荐码（可选）';

  @override
  String get signUpReferralCreditsNotGrantedBody =>
      '我们未能发放你的推荐积分。如有任何疑问，请联系我们寻求帮助。';

  @override
  String get signUpReferralCreditsNotGrantedTitle => '推荐积分未发放';

  @override
  String get signUpReferralInvalidBody =>
      '你的推荐码似乎无效。请检查后稍后重试，或将其移除。如有任何疑问，欢迎通过 hi@vicoa.ai 联系我。';

  @override
  String get signUpReferralInvalidTitle => '推荐码应用失败';

  @override
  String get signUpRemoveReferralCode => '删除推荐码';

  @override
  String get signUpSignInLink => '登录';

  @override
  String get signUpSignUpLink => '注册';

  @override
  String signUpSubtitleSignIn(Object phrase) {
    return '登录即可在手机上拥有一个AI编程和助手团队';
  }

  @override
  String get signUpSubtitleSignUp => '注册即可在手机上拥有一个AI编程和助手团队';

  @override
  String get startSessionAgent => 'Agent';

  @override
  String startSessionAgentComingSoon(Object name) {
    return '$name（即将支持）';
  }

  @override
  String get startSessionLoadingMachines => '正在加载机器…';

  @override
  String get startSessionMachine => '机器';

  @override
  String get startSessionNewSession => '新任务';

  @override
  String get startSessionOffline => '（离线）';

  @override
  String get startSessionOrSeparator => ' 或 ';

  @override
  String get startSessionRecent => '最近';

  @override
  String get startSessionRunPrefix => '运行 ';

  @override
  String get startSessionSelectMachine => '选择一台机器';

  @override
  String get startSessionShowMore => '显示更多';

  @override
  String get startSessionStartSession => '开始任务';

  @override
  String get startSessionStartedNoStatus => '任务已启动，但无法确定状态。请重试。';

  @override
  String get startSessionToBringOnline => ' 让你的机器上线。';

  @override
  String get startSessionUnableToStart => '无法启动任务';

  @override
  String get startSessionUnableToStartBody =>
      '可能的原因：\n\n• 机器无响应\n• 网络连接问题\n• 目录路径无效\n\n请检查机器状态后重试。';

  @override
  String get startSessionWorkingDirectory => '工作目录';

  @override
  String get surveyDefaultQuestion => '你的目标是什么？';

  @override
  String get surveyOpt1to2h => '1–2 小时';

  @override
  String get surveyOpt2to4h => '2–4 小时';

  @override
  String get surveyOpt4to8h => '4–8 小时';

  @override
  String get surveyOptCodePhone => '📱 我想用手机编程';

  @override
  String get surveyOptDataScientist => '数据科学家 / 分析师';

  @override
  String get surveyOptResearcher => '研究员';

  @override
  String get surveyOptDesign => '设计';

  @override
  String get surveyOptDeveloper => '开发者';

  @override
  String get surveyOptFinance => '财务';

  @override
  String get surveyOptFounder => '创始人';

  @override
  String get surveyOptFreelancer => '自由职业者';

  @override
  String get surveyOptGt8h => '>8 小时';

  @override
  String get surveyOptLoseTrack => '🔀 我无法及时了解各个 Agent 的状态';

  @override
  String get surveyOptLt1h => '<1 小时';

  @override
  String get surveyOptMarketing => '市场营销';

  @override
  String get surveyOptNoComputer => '我不用电脑';

  @override
  String get surveyOptNotAtComputer => '📍 我无法总是在电脑前';

  @override
  String get surveyOptOthers => '其他';

  @override
  String get surveyOptProduct => '产品';

  @override
  String get surveyOptStuckDesk => '🖥️ 我只能在电脑上使用 AI 编程';

  @override
  String get surveyOptStudent => '学生';

  @override
  String get surveyOptTooManySessions => '🤯 我要同时管理太多 AI 编程助手';

  @override
  String get surveyOptWaitAi => '⏳ 我经常等待 AI 完成任务';

  @override
  String get surveyQAiTools => '你使用哪些\nAI 编程工具？';

  @override
  String get surveyQDailyTime => '你每天平均有多少时间\n在AI编程？';

  @override
  String get surveyQDescribeYou => '以下哪项最符合你？';

  @override
  String get surveyQOs => '你的电脑的\n操作系统是？';

  @override
  String get surveyQResonate => '以下哪些\n让你有共鸣？';

  @override
  String get surveySelectAllThatApply => '选择所有适用项';

  @override
  String get surveyTypeYourAnswer => '输入你的答案……';

  @override
  String get surveyWithImpactMotivationAlerts => '太好了，AI 完成任务后，Vicoa 会第一时间通知你。';

  @override
  String get surveyWithImpactMotivationCodeFromPhone =>
      '太好了，Vicoa 让你在手机上与 AI 一起编程。';

  @override
  String get surveyWithImpactMotivationDefault =>
      '太好了，Vicoa 让你随时随地，在手机上使用 AI 编程。';

  @override
  String get surveyWithImpactMotivationFreeFromDesk =>
      '太好了，Vicoa 让你离开办公桌后，继续和 AI 协作。';

  @override
  String get surveyWithImpactMotivationMultipleAgents =>
      '太好了，Vicoa 帮你轻松管理多个 AI Agent。';

  @override
  String get surveyWithImpactMotivationOnTrack =>
      '太好了，Vicoa 让你轻松了解 Agent 状态，同时推进任务。';

  @override
  String get surveyWithImpactMotivationSendCommands =>
      '太好了，Vicoa 会通知你，并让你立即接管任务。';

  @override
  String get tutorialTitle => '教程';

  @override
  String usageCreditsCanStillSend(Object count) {
    return '你还可以免费发送 $count 条消息。';
  }

  @override
  String get usageCreditsFreeMessages => '免费消息';

  @override
  String get usageCreditsGetMoreFreeMessages => '获取更多免费消息';

  @override
  String get usageCreditsGiftComingSoon => '即将上线：把你的免费消息赠送给好友！';

  @override
  String get usageCreditsInviteFriends => '邀请好友';

  @override
  String get usageCreditsLearnMore => '了解更多';

  @override
  String get usageCreditsRateUs5Stars => '给我们五星好评';

  @override
  String get usageCreditsStartFreeTrialNow => '立即开始免费试用 👋';

  @override
  String get usageCreditsUnlimitedMessagesAgents => '无限消息与 Agent';

  @override
  String get usageCreditsYourMessages => '我的消息';

  @override
  String get versionUpdateDialogBody => 'Vicoa 有新版本可用。请更新 App 以使用全部精彩功能。';

  @override
  String get versionUpdateDialogLater => '稍后再说';

  @override
  String get versionUpdateDialogTitle => '有新版本可用';

  @override
  String get versionUpdateDialogUpdateNow => '立即更新';

  @override
  String get videoPlayerXError => '视频播放出错';

  @override
  String get videoPlayerXLoading => '加载中';

  @override
  String get voiceAssistanceDescription => '选择聊天中语音输入所使用的语言。';

  @override
  String get voiceAssistanceTitle => '语音助手';

  @override
  String get voiceAssistanceTranscriptionLanguage => '语言';

  @override
  String get voiceLanguageSearchHint => '搜索语言';

  @override
  String get voiceLanguageTitle => '语音语言';

  @override
  String get webPreviewBeta => 'beta';

  @override
  String get webPreviewEnterUrl => '输入网址';

  @override
  String webPreviewHttpStatus(Object statusCode) {
    return '服务器返回 HTTP $statusCode。';
  }

  @override
  String get webPreviewSiteUnreachable => '无法访问此网站';

  @override
  String get webPreviewTitle => '实时预览';

  @override
  String webPreviewUrlUnreachableDetails(Object details) {
    return '无法访问此网址。$details';
  }

  @override
  String get webPreviewUrlUnreachableHint =>
      '无法访问此网址。请检查预览服务器是否正在运行，以及隧道网址是否仍然有效。';

  @override
  String get webPreviewWebUnavailable => '网页预览仅在 iOS/Android 应用版本中可用。';

  @override
  String get welcomeAnswerQuickQuestions => '回答几个简单的问题\n为你定制专属体验';

  @override
  String welcomeDemoCancelSubscription(Object url) {
    return '温馨提示：Vicoa 需要在电脑上运行，所以如果你正在试用，可能需要**取消试用以免被扣费**。\n\n[如何取消订阅 →]($url)';
  }

  @override
  String get welcomeDemoCardTapToSee => '了解 Vicoa 的工作方式';

  @override
  String get welcomeDemoCardWelcome => '欢迎使用 Vicoa';

  @override
  String get welcomeDemoCta => '准备好尝试了吗？选择适合你的方式：';

  @override
  String get welcomeDemoInstanceName => '欢迎使用 Vicoa 👋';

  @override
  String get welcomeDemoLatestMessage => '准备好了就开始吧 —— 选择你想要的入门方式。';

  @override
  String get welcomeDemoMsg1 =>
      '👋 **欢迎使用 Vicoa！**\n\nVicoa 让你随时随地，同时操控多个 AI Agent 完成任务。\n\n下面是一些示例对话 👇';

  @override
  String get welcomeDemoMsg2 => '我怎么使用 Vicoa？';

  @override
  String get welcomeDemoMsg3 =>
      '📱 **方式1: 在手机上**：点击 **+** 按钮，新建一个任务。\n\n🖥️ **方式2: 在电脑上**：终端启动任务，再到手机上继续。\n';

  @override
  String get welcomeDemoMsg4 => '我能做些什么？';

  @override
  String get welcomeDemoMsg5 =>
      '- 💬 与你的 AI agent 对话\n- 🔔 任务完成时收到通知\n- ✅ 批准操作\n- 👀 查看文件和代码变更\n- 还有更多……';

  @override
  String get welcomeDemoMsg8 => 'Vicoa 支持哪些 AI Agent？';

  @override
  String get welcomeDemoMsg9 =>
      '主流的 AI Agent：\n| Agent | 模型 |\n| --- | --- |\n| Claude Code | 如 Opus 4.8、Opus 4.7、Sonnet 4.6 |\n| Codex | 如 GPT-5.5、GPT-5.4 |\n| OpenCode | 如 Z.AI、Minimax、DeepSeek |\n| Gemini | 如 Gemini 3 Pro、Gemini 2.5 Flash |\n| Cursor | 如 Composer、Claude、GPT |\n| Copilot | 如 Claude、GPT、Gemini |\n| Kimi | 如 Kimi K2.5、K2.6、K2.7 Code |\n| Hermes | 50+ 个模型 |\n\n Vicoa 实时展示 AI Agent 做的改动：\n\n';

  @override
  String get welcomeDemoNoComputerSubtitle => '告诉我们你想要什么';

  @override
  String get welcomeDemoNoComputerTitle => '我的电脑没在身边';

  @override
  String get welcomeDemoSetupCliSubtitle => '给我发一封含上手链接的邮件';

  @override
  String get welcomeDemoSetupCliTitle => '我会在电脑上安装 Vicoa';

  @override
  String welcomeDemoSetupEmailSent(Object target) {
    return '📧 我们已经把入门链接发送到 $target。\n\n';
  }

  @override
  String get welcomeDemoSetupEmailTargetFallback => '你的邮箱';

  @override
  String get welcomeDemoSetupInstructions =>
      '以下是在电脑上完成配置的步骤：\n\n1. 下载桌面应用：**https://vicoa.ai/download**\n2. 打开并登录，你的电脑会自动连接\n\n更习惯命令行？请查看[安装指南](https://vicoa.ai/docs/getting-started)。\n\n';

  @override
  String get welcomeDemoSetupQuestion => '我该怎么开始？';

  @override
  String get welcomeDemoWaitlistHeader => '简单问一下';

  @override
  String get welcomeDemoWaitlistIntro =>
      '没关系。Vicoa 现在需要现在电脑上安装插件，但我们正在开发更多功能。告诉我们你的需求，我们会及时通知你：';

  @override
  String get welcomeDemoWaitlistOptDev => '我是开发者，只是现在身边没有电脑';

  @override
  String get welcomeDemoWaitlistOptGithub => '我是开发者，想连接 GitHub，完全在手机上用';

  @override
  String get welcomeDemoWaitlistOptNotDev => '我不是开发者，只想在手机上做应用';

  @override
  String get welcomeDemoWaitlistPrompt => '加入等候名单';

  @override
  String get welcomeDemoWaitlistQuestion => '你想用 Vicoa 做什么？';

  @override
  String get welcomeDemoWaitlistThanks =>
      '🙌 谢谢！你已加入名单。一旦有适合你的上手方式，我们会第一时间联系你。';

  @override
  String get welcomeGladToHaveYou => '欢迎加入 👋';

  @override
  String get welcomeSkipForNow => '暂时跳过';

  @override
  String get welcomeStartYourJourney => '开启你的旅程，\n随时随地畅快编程。';

  @override
  String get worktreeActionsActiveSession => '此工作树中仍有任务在运行。';

  @override
  String get worktreeActionsCleanupContent =>
      '此任务在 vicoa工作树中运行，且没有剩余更改。删除该工作树，还是保留这些文件？';

  @override
  String get worktreeActionsCleanupTitle => '删除工作树？';

  @override
  String get worktreeActionsDeleted => '已删除工作树。';

  @override
  String worktreeActionsRemoveContent(Object branch) {
    return '移除工作树“$branch”吗？分支会被保留，因此上面的提交仍然安全。';
  }

  @override
  String worktreeActionsRemoveDirtyContent(Object branch) {
    return '工作树“$branch”有未提交的更改。仍要移除吗？分支会被保留，因此上面的提交仍然安全。';
  }

  @override
  String get worktreeActionsRemoveFailed => '无法移除工作树。';

  @override
  String worktreeActionsRemoveFailedCode(Object code) {
    return '无法移除工作树：$code';
  }

  @override
  String get worktreeActionsRemoveTitle => '移除工作树';

  @override
  String get worktreeActionsRemoved => '已移除工作树。';

  @override
  String get worktreeActionsThisWorktree => '此工作树';

  @override
  String get worktreeDetailBranch => '分支';

  @override
  String get worktreeDetailCopyPath => '复制路径';

  @override
  String get worktreeDetailInUseDescription => '此工作树中仍有任务在运行。请先结束任务再移除。';

  @override
  String get worktreeDetailNotManagedNote => '此工作树不是由 Vicoa 创建的，因此无法在 App 内管理。';

  @override
  String get worktreeDetailOrigin => '来源';

  @override
  String get worktreeDetailOriginExternal => '外部';

  @override
  String get worktreeDetailOriginVicoa => 'Vicoa';

  @override
  String get worktreeDetailPath => '路径';

  @override
  String get worktreeDetailPathCopied => '路径已复制到剪贴板';

  @override
  String get worktreeDetailRemoveDescription => '移除该工作树的检出。分支会保留，因此提交不会丢失。';

  @override
  String get worktreeDetailRemoveWorktree => '移除工作树';

  @override
  String get worktreeDetailStatus => '状态';

  @override
  String get worktreeDetailStatusIdle => '空闲';

  @override
  String get worktreeDetailStatusInUse => '使用中，有任务正在运行';

  @override
  String get worktreeDetailWorktree => '工作树';

  @override
  String get worktreePickerCurrentBranch => '当前分支';

  @override
  String get worktreePickerCurrentBranchSubtitle => '不使用工作树· 在该目录中运行';

  @override
  String get worktreePickerDetached => '（游离）';

  @override
  String get worktreePickerExistingWorktrees => '现有工作树';

  @override
  String worktreePickerExternalPath(Object path) {
    return '$path · 外部';
  }

  @override
  String get worktreePickerLoadFailed => '无法加载工作树';

  @override
  String get worktreePickerNewWorktree => '新建工作树';

  @override
  String get worktreePickerNewWorktreeSubtitle => '从 HEAD 拉出一个新分支';

  @override
  String get worktreePickerNotARepo => '该目录不是 git 仓库 —— 仅可使用当前分支。';

  @override
  String get worktreePickerWorktree => '工作树';

  @override
  String get worktreesCouldNotLoad => '无法加载工作树';

  @override
  String get worktreesDetached => '(detached)';

  @override
  String get worktreesNoWorktreesSubtitle => '在新工作树中开始任务即可创建一个，创建后会显示在这里供你管理。';

  @override
  String get worktreesNoWorktreesYet => '暂无工作树';

  @override
  String get worktreesNotAGitRepo => '不是 git 仓库';

  @override
  String get worktreesNotAGitRepoSubtitle => '此目录不是 git 仓库。';

  @override
  String get worktreesPullToRefresh => '下拉刷新以重试。';

  @override
  String get worktreesTitle => '工作树';

  @override
  String get worktreesWorktreeRemoved => '工作树已移除。';

  @override
  String get youtubeXInvalidUrl => '无效的 YouTube 链接';

  @override
  String get youtubeXNoVideoUrl => '未提供视频链接';

  @override
  String get sessionUsageTitle => '用量';

  @override
  String get sessionUsageContext => '上下文窗口';

  @override
  String get sessionUsageTokensSuffix => 'tokens';

  @override
  String sessionUsageSessionCost(Object cost) {
    return '会话费用 $cost';
  }

  @override
  String get sessionUsageCredits => '额度';

  @override
  String sessionUsageCreditsLeft(Object amount) {
    return '剩余 $amount';
  }

  @override
  String sessionUsageResetsAtTime(Object time) {
    return '$time 重置';
  }

  @override
  String sessionUsageResetsOnDate(Object date, Object time) {
    return '$date$time 重置';
  }

  @override
  String get sessionUsageResettingNow => '即将重置';

  @override
  String get sessionUsageRefreshing => '刷新中…';

  @override
  String get automationsAgent => '智能体';

  @override
  String get automationsAtMinute => '分钟';

  @override
  String get automationsChooseFolder => '选择文件夹';

  @override
  String get automationsConnectMachineFirst => '请先连接一台机器再创建自动化。';

  @override
  String get automationsCouldNotLoad => '无法加载自动化';

  @override
  String get automationsDate => '日期';

  @override
  String get automationsDelete => '删除';

  @override
  String get automationsDeleteConfirmBody => '将删除该自动化及其运行记录，已启动的任务会保留。';

  @override
  String get automationsDeleteConfirmTitle => '删除自动化？';

  @override
  String get automationsDeleted => '已删除自动化';

  @override
  String get automationsEditTitle => '编辑自动化';

  @override
  String get automationsEmptySubtitle => '让智能体定时自动运行';

  @override
  String get automationsEmptyTitle => '还没有自动化';

  @override
  String get automationsEvery => '每';

  @override
  String automationsEveryUnitDays(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '天',
    );
    return '$_temp0';
  }

  @override
  String automationsEveryUnitHours(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '小时',
    );
    return '$_temp0';
  }

  @override
  String automationsEveryUnitMinutes(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '分钟',
    );
    return '$_temp0';
  }

  @override
  String automationsEveryUnitMonths(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '个月',
    );
    return '$_temp0';
  }

  @override
  String automationsEveryUnitWeeks(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '周',
    );
    return '$_temp0';
  }

  @override
  String get automationsFilterActive => '运行中';

  @override
  String get automationsFilterAll => '全部';

  @override
  String get automationsFilterPaused => '已暂停';

  @override
  String get automationsMachineOffline => '机器离线，无法启动运行。';

  @override
  String get automationsNew => '新建自动化';

  @override
  String automationsNextRun(String when) {
    return '下次 · $when';
  }

  @override
  String get automationsNoRunsYet => '暂无运行记录。';

  @override
  String get automationsPause => '暂停';

  @override
  String get automationsProject => '项目';

  @override
  String get automationsPromptPlaceholder => '描述智能体要做什么';

  @override
  String get automationsPullToRefresh => '下拉重试';

  @override
  String get automationsRepeat => '重复';

  @override
  String get automationsRepeatCustom => '自定义';

  @override
  String get automationsRepeatDaily => '每天';

  @override
  String get automationsRepeatHourly => '每小时';

  @override
  String get automationsRepeatMinutely => '每分钟';

  @override
  String get automationsRepeatMonthly => '每月';

  @override
  String get automationsRepeatOnce => '一次';

  @override
  String get automationsRepeatWeekdays => '工作日';

  @override
  String get automationsRepeatWeekly => '每周';

  @override
  String get automationsRepeats => '重复单位';

  @override
  String get automationsResume => '恢复';

  @override
  String get automationsRunFailed => '运行失败';

  @override
  String get automationsRunNow => '立即运行';

  @override
  String get automationsRunStarted => '已开始运行';

  @override
  String get automationsRunStatusFailed => '失败';

  @override
  String get automationsRunStatusFired => '已运行';

  @override
  String get automationsRunStatusMissedOffline => '未运行——离线';

  @override
  String get automationsRunStatusSkipped => '已跳过';

  @override
  String get automationsRunsOn => '运行机器';

  @override
  String get automationsSaveFailed => '保存自动化失败';

  @override
  String automationsScheduleOnceAt(String when) {
    return '一次 · $when';
  }

  @override
  String get automationsSectionDetails => '详情';

  @override
  String get automationsSectionFrequency => '频率';

  @override
  String get automationsSectionRunHistory => '运行记录';

  @override
  String get automationsStatusPaused => '已暂停';

  @override
  String automationsSummaryDaily(String time) {
    return '每天 $time';
  }

  @override
  String automationsSummaryEveryDays(String n, String time) {
    return '每 $n 天 $time';
  }

  @override
  String automationsSummaryEveryHours(String n, String minute) {
    return '每 $n 小时 :$minute';
  }

  @override
  String automationsSummaryEveryMonths(String n, String days, String time) {
    return '每 $n 个月 $days 号 $time';
  }

  @override
  String automationsSummaryEveryWeeks(String n, String days, String time) {
    return '每 $n 周 $days $time';
  }

  @override
  String automationsSummaryHourly(String minute) {
    return '每小时 :$minute';
  }

  @override
  String get automationsSummaryHourlyPlain => '每小时';

  @override
  String automationsSummaryEveryHoursPlain(String n) {
    return '每 $n 小时';
  }

  @override
  String automationsSummaryEveryMinutes(String n) {
    return '每 $n 分钟';
  }

  @override
  String get automationsSummaryRecurring => '定期';

  @override
  String automationsSummaryWeekdays(String time) {
    return '工作日 $time';
  }

  @override
  String automationsSummaryWeekly(String days, String time) {
    return '每周 $days $time';
  }

  @override
  String get automationsTime => '时间';

  @override
  String get automationsTimeWindow => '时间段';

  @override
  String get automationsWindowAllDay => '全天';

  @override
  String get automationsWindowCustom => '自定义';

  @override
  String get automationsWindowFrom => '从';

  @override
  String get automationsWindowInvalid => '结束时间必须晚于开始时间。';

  @override
  String get automationsWindowTo => '至';

  @override
  String get automationsTitle => '自动化';

  @override
  String get automationsTitlePlaceholder => '自动化标题';

  @override
  String get automationsTitleRequired => '请输入标题';

  @override
  String get tabAgents => '任务';

  @override
  String get tabAutomations => '自动化';

  @override
  String get tabProfile => '我的';

  @override
  String get tabTasks => '待办';

  @override
  String get searchHint => '搜索任务、待办、自动化';

  @override
  String get searchRecent => '最近';

  @override
  String get searchSessions => '任务';

  @override
  String get searchNoResults => '未找到结果';

  @override
  String get searchPrompt => '输入以搜索任务、待办和自动化';

  @override
  String get searchFailed => '搜索失败,请检查网络后重试';

  @override
  String get searchTimeout => '搜索超时,请尝试更精确的关键词';

  @override
  String get searchSessionsOnly => '仅显示任务';

  @override
  String get gettingStartedTitle => '开始使用';

  @override
  String gettingStartedProgress(int done, int total) {
    return '已完成 $done/$total';
  }

  @override
  String get gettingStartedConnectTitle => '连接一台电脑';

  @override
  String get gettingStartedConnectHint => '在电脑上安装 Vicoa';

  @override
  String get gettingStartedSessionTitle => '开启一个对话';

  @override
  String get gettingStartedSessionHint => '用 Vicoa 启动一个智能体会话';

  @override
  String get gettingStartedMessageTitle => '发送一条消息';

  @override
  String get gettingStartedMessageHint => '与你的智能体对话';

  @override
  String get gettingStartedCollapse => '收起';

  @override
  String get gettingStartedDismiss => '关闭';

  @override
  String get gettingStartedConnectSheetTitle => '在电脑上配置 Vicoa';

  @override
  String get gettingStartedConnectSheetBody =>
      'Vicoa 在你的电脑上运行智能体。先在电脑上安装桌面版,然后就能在手机上启动、查看并和它们对话。';

  @override
  String get gettingStartedEmailLinkCta => '把安装链接发到我邮箱';

  @override
  String get gettingStartedEmailSentCta => '链接已发送';

  @override
  String gettingStartedEmailSentToast(Object target) {
    return '我们已将链接发送到 $target。';
  }

  @override
  String get gettingStartedDownloadCta => '或访问 vicoa.ai/download';
}
