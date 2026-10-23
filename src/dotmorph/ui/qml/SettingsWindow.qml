import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Controls.Basic as QC

// `dotmorph settings`: every option of DotMorph in one place. `backend` is
// settings_window.SettingsBackend; every change is saved immediately.
Window {
    id: win
    width: 900
    height: 620
    minimumWidth: 740
    minimumHeight: 480
    visible: true
    title: theme.t("DotMorph Settings")
    color: theme.window

    LayoutMirroring.enabled: theme.rtl
    LayoutMirroring.childrenInherit: true

    Theme {
        id: theme
        name: backend.theme
        reduceMotion: backend.reduceMotion
    }
    property alias th: theme  // for children that have their own `theme` property

    property int page: 0
    readonly property var pages: [
        { key: "General", icon: "general" },
        { key: "Wheel", icon: "wheel" },
        { key: "Shortcut", icon: "keyboard" },
        { key: "Integrations", icon: "plug" },
        { key: "Watch folders", icon: "folder" },
        { key: "Tools", icon: "wrench" },
        { key: "About", icon: "info" },
    ]
    function open(url) { Qt.openUrlExternally(url) }

    FolderDialog {
        id: outputDialog
        onAccepted: backend.set("outputDir", selectedFolder.toString())
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ---- sidebar --------------------------------------------------------------------
        Rectangle {
            Layout.preferredWidth: 230
            Layout.fillHeight: true
            color: theme.card
            Rectangle {  // divider on the content side
                width: 1
                height: parent.height
                anchors.right: parent.right
                color: theme.cardEdge
            }

            Column {
                x: 16
                y: 20
                width: parent.width - 32
                spacing: 6

                Row {
                    spacing: 12
                    bottomPadding: 18
                    Image {
                        source: "../icons/dotmorph.svg"
                        sourceSize: Qt.size(40, 40)
                        width: 40
                        height: 40
                    }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        Text { text: "DotMorph"; color: theme.text; font.pixelSize: 17; font.bold: true }
                        Text {
                            text: theme.t("Version %1", backend.version)
                            color: theme.textDim
                            font.pixelSize: 11
                        }
                    }
                }

                Repeater {
                    model: win.pages
                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        readonly property bool on: win.page === index
                        objectName: "nav-" + modelData.icon
                        width: parent.width
                        height: 40
                        radius: 12
                        color: on ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.14)
                                  : (navHit.containsMouse ? Qt.rgba(0.5, 0.5, 0.5, 0.10) : "transparent")
                        Behavior on color { ColorAnimation { duration: theme.ms(120) } }
                        Rectangle {  // active marker
                            visible: parent.on
                            width: 3
                            height: 18
                            radius: 1.5
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            color: theme.accent
                        }
                        Row {
                            anchors.left: parent.left
                            anchors.leftMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 12
                            CategoryIcon {
                                width: 18
                                height: 18
                                category: modelData.icon
                                color: parent.parent.on ? theme.accent : theme.textDim
                            }
                            Text {
                                text: theme.t(modelData.key)
                                color: parent.parent.on ? theme.text : theme.textDim
                                font.pixelSize: 13
                                font.bold: parent.parent.on
                            }
                        }
                        MouseArea {
                            id: navHit
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: win.page = index
                        }
                    }
                }
            }

            Text {  // DotSuite tag at the bottom of the sidebar
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 18
                anchors.left: parent.left
                anchors.leftMargin: 18
                text: "DOT<font color='" + theme.text + "'>SUITE</font>"
                textFormat: Text.StyledText
                color: theme.accent
                font.pixelSize: 12
                font.bold: true
                font.letterSpacing: 2
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: win.open("https://dotsuite.dev/en")
                }
            }
        }

        // ---- page -----------------------------------------------------------------------
        Flickable {
            id: flick
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentHeight: loader.height + 56
            boundsBehavior: Flickable.StopAtBounds
            QC.ScrollBar.vertical: QC.ScrollBar { }

            Loader {
                id: loader
                objectName: "pageLoader"
                x: 32
                y: 28
                width: flick.width - 64
                sourceComponent: [generalPage, wheelPage, shortcutPage, integrationsPage,
                                  watchPage, toolsPage, aboutPage][win.page]
                onLoaded: flick.contentY = 0
            }
        }
    }

    component PageTitle: Text {
        color: theme.text
        font.pixelSize: 24
        font.bold: true
        bottomPadding: 4
    }

    component Pill: Rectangle {
        property string text: ""
        property bool good: true
        width: pillText.implicitWidth + 18
        height: 24
        radius: 12
        color: good ? Qt.rgba(0.06, 0.73, 0.51, 0.14) : Qt.rgba(1, 0.36, 0.48, 0.14)
        border.color: good ? theme.accent : theme.danger
        Text {
            id: pillText
            anchors.centerIn: parent
            text: parent.text
            color: parent.good ? theme.accent : theme.danger
            font.pixelSize: 11
            font.bold: true
        }
    }

    // =========================================================================== General
    Component {
        id: generalPage
        Column {
            spacing: 18
            PageTitle { text: theme.t("General") }

            SetCard {
                title: theme.t("Appearance")
                RowLayout {
                    width: parent.width
                    spacing: 20
                    Column {
                        Layout.fillWidth: true
                        spacing: 16
                        SetRow {
                            label: theme.t("Theme")
                            Seg {
                                objectName: "themeChoice"
                                options: [{ value: "dark", text: theme.t("Dark") },
                                          { value: "light", text: theme.t("Light") },
                                          { value: "glass", text: theme.t("Glass") }]
                                current: backend.theme
                                onChosen: (v) => backend.set("theme", v)
                            }
                        }
                        SetRow {
                            label: theme.t("Reduce motion")
                            hint: theme.t("No animations in the wheel")
                            Toggle {
                                checked: backend.reduceMotion
                                onToggled: (on) => backend.set("reduceMotion", on)
                            }
                        }
                        SetRow {
                            label: theme.t("Language")
                            Seg {
                                objectName: "languageChoice"
                                options: [{ value: "auto", text: theme.t("System") },
                                          { value: "en", text: "English" },
                                          { value: "ar", text: "العربية" }]
                                current: backend.language
                                onChosen: (v) => backend.set("language", v)
                            }
                        }
                    }
                    // live preview of the wheel in the chosen theme
                    Item {
                        Layout.preferredWidth: 170
                        Layout.preferredHeight: 170
                        Rectangle {
                            anchors.centerIn: parent
                            width: 168
                            height: 168
                            radius: 84
                            color: theme.backdrop
                            border.color: theme.backdropEdge
                        }
                        Repeater {
                            model: ["image", "video", "audio", "document", "tools"]
                            delegate: RingSector {
                                required property var modelData
                                required property int index
                                theme: win.th
                                innerR: 36
                                outerR: 76
                                startDeg: index * 72 - 36
                                sweepDeg: 72
                                gapPx: 3
                                category: modelData
                                showIcon: true
                                hovered: index === 1
                                order: index
                            }
                        }
                        Rectangle {
                            anchors.centerIn: parent
                            width: 60
                            height: 60
                            radius: 30
                            color: theme.hub
                            border.color: theme.accent
                        }
                    }
                }
            }

            SetCard {
                title: theme.t("Notifications")
                SetRow {
                    label: theme.t("When a conversion finishes")
                    Seg {
                        options: [{ value: "long", text: theme.t("Long jobs") },
                                  { value: "always", text: theme.t("Always") },
                                  { value: "never", text: theme.t("Never") }]
                        current: backend.notify
                        onChosen: (v) => backend.set("notify", v)
                    }
                }
            }

            SetCard {
                title: theme.t("Save converted files")
                SetRow {
                    label: backend.outputDir
                    Seg {
                        options: [{ value: "beside", text: theme.t("Next to the original") },
                                  { value: "folder", text: theme.t("In a folder") }]
                        current: backend.outputDir === "" ? "beside" : "folder"
                        onChosen: (v) => v === "beside" ? backend.set("outputDir", "") : outputDialog.open()
                    }
                }
            }

            SetCard {
                title: theme.t("Default options")
                SetRow {
                    label: theme.t("Quality")
                    SetSlider {
                        value: backend.quality
                        onMoved: (v) => backend.set("quality", v)
                    }
                }
                SetRow {
                    label: theme.t("Resolution (PDF / SVG)")
                    Seg {
                        options: [{ value: 0, text: theme.t("Auto") }, { value: 72, text: "72" },
                                  { value: 150, text: "150" }, { value: 300, text: "300" }]
                        current: backend.dpi
                        onChosen: (v) => backend.set("dpi", v)
                    }
                }
                SetRow {
                    label: theme.t("Size")
                    Seg {
                        options: [{ value: "", text: theme.t("Original") }, { value: "75%", text: "75%" },
                                  { value: "50%", text: "50%" }, { value: "25%", text: "25%" }]
                        current: backend.resize
                        onChosen: (v) => backend.set("resize", v)
                    }
                }
                SetRow {
                    label: theme.t("Remove metadata")
                    hint: theme.t("EXIF, GPS, tags")
                    Toggle {
                        checked: backend.strip
                        onToggled: (on) => backend.set("strip", on)
                    }
                }
            }
        }
    }

    // ============================================================================= Wheel
    Component {
        id: wheelPage
        Column {
            spacing: 18
            PageTitle { text: theme.t("Wheel") }
            SetCard {
                title: theme.t("Your formats")
                subtitle: theme.t("Click a format: once to pin it (shown first), twice to hide it, again to reset.")

                Repeater {
                    model: ["image", "video", "audio", "document", "tools"]
                    delegate: Column {
                        required property var modelData
                        readonly property string cat: modelData
                        width: parent.width
                        spacing: 8
                        Text {
                            text: theme.categoryLabel(parent.cat)
                            color: theme.categoryColor(parent.cat)
                            font.pixelSize: 12
                            font.bold: true
                        }
                        Flow {
                            width: parent.width
                            spacing: 8
                            Repeater {
                                model: backend.formats.filter(function (f) { return f.category === parent.parent.cat })
                                delegate: Rectangle {
                                    required property var modelData
                                    readonly property bool pinned: modelData.state === "pinned"
                                    readonly property bool hiddenF: modelData.state === "hidden"
                                    objectName: "chip-" + modelData.id
                                    width: chipText.implicitWidth + 26
                                    height: 30
                                    radius: 15
                                    opacity: hiddenF ? 0.45 : 1
                                    color: pinned ? theme.accent : Qt.rgba(0.5, 0.5, 0.5, chipHit.containsMouse ? 0.18 : 0.08)
                                    border.color: pinned ? Qt.lighter(theme.accent, 1.2) : theme.cardEdge
                                    Text {
                                        id: chipText
                                        anchors.centerIn: parent
                                        text: (parent.pinned ? "★ " : "") + modelData.label
                                        color: parent.pinned ? "#0A0A0A" : theme.text
                                        font.pixelSize: 12
                                        font.bold: parent.pinned
                                        font.strikeout: parent.hiddenF
                                    }
                                    MouseArea {
                                        id: chipHit
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: backend.cycleFormat(parent.modelData.id)
                                    }
                                }
                            }
                        }
                    }
                }
                Row {
                    spacing: 16
                    Text { text: "★ " + theme.t("Pinned"); color: theme.accent; font.pixelSize: 12 }
                    Text { text: theme.t("Hidden"); color: theme.textDim; font.pixelSize: 12; font.strikeout: true }
                }
                Btn {
                    text: theme.t("Clear")
                    onClicked: backend.clearFormats()
                }
            }
        }
    }

    // ========================================================================== Shortcut
    Component {
        id: shortcutPage
        Column {
            spacing: 18
            PageTitle { text: theme.t("Shortcut") }
            SetCard {
                title: theme.t("Global shortcut")
                subtitle: theme.t("Opens the wheel with the files you copied in your file manager.")

                SetRow {
                    label: theme.t("Current shortcut")
                    Row {
                        spacing: 6
                        Repeater {
                            model: backend.hotkey === "" ? [theme.t("Not set")]
                                 : backend.hotkey.replace(/></g, ",").replace(/[<>]/g, ",").split(",").filter(function (k) { return k !== "" })
                            delegate: Rectangle {
                                required property var modelData
                                width: keyText.implicitWidth + 20
                                height: 30
                                radius: 8
                                color: theme.window
                                border.color: theme.cardEdge
                                Text {
                                    id: keyText
                                    anchors.centerIn: parent
                                    text: modelData.length === 1 ? modelData.toUpperCase() : modelData
                                    color: theme.text
                                    font.pixelSize: 12
                                    font.bold: true
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    id: recorder
                    objectName: "hotkeyRecorder"
                    visible: backend.hotkeySupported
                    property bool recording: false
                    property string message: ""
                    width: parent.width
                    height: 64
                    radius: 14
                    color: recording ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.10) : theme.window
                    border.width: recording ? 2 : 1
                    border.color: recording ? theme.accent : theme.cardEdge
                    Text {
                        anchors.centerIn: parent
                        text: recorder.recording ? theme.t("Press the keys now…")
                              : (recorder.message !== "" ? recorder.message : theme.t("Record a new shortcut"))
                        color: recorder.recording ? theme.accent : theme.text
                        width: parent.width - 32
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                        font.pixelSize: 13
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: { recorder.recording = true; recorder.message = ""; recorder.forceActiveFocus() }
                    }
                    function keyName(e) {
                        var k = e.key
                        if (k >= Qt.Key_A && k <= Qt.Key_Z) return String.fromCharCode(k).toLowerCase()
                        if (k >= Qt.Key_0 && k <= Qt.Key_9) return String.fromCharCode(k)
                        if (k >= Qt.Key_F1 && k <= Qt.Key_F35) return "F" + (k - Qt.Key_F1 + 1)
                        var names = {}
                        names[Qt.Key_Space] = "space"; names[Qt.Key_Return] = "Return"; names[Qt.Key_Tab] = "Tab"
                        names[Qt.Key_Delete] = "Delete"; names[Qt.Key_Insert] = "Insert"; names[Qt.Key_Home] = "Home"
                        names[Qt.Key_End] = "End"; names[Qt.Key_PageUp] = "Page_Up"; names[Qt.Key_PageDown] = "Page_Down"
                        names[Qt.Key_Left] = "Left"; names[Qt.Key_Right] = "Right"; names[Qt.Key_Up] = "Up"
                        names[Qt.Key_Down] = "Down"; names[Qt.Key_Print] = "Print"; names[Qt.Key_Comma] = "comma"
                        names[Qt.Key_Period] = "period"; names[Qt.Key_Slash] = "slash"; names[Qt.Key_Minus] = "minus"
                        names[Qt.Key_Equal] = "equal"
                        return names[k] || ""
                    }
                    Keys.onPressed: (e) => {
                        if (!recording) return
                        e.accepted = true
                        if (e.key === Qt.Key_Escape) { recording = false; return }
                        var mods = [Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_Super_L,
                                    Qt.Key_Super_R, Qt.Key_AltGr]
                        if (mods.indexOf(e.key) >= 0) return  // wait for the real key
                        var name = keyName(e)
                        var accel = ""
                        if (e.modifiers & Qt.ControlModifier) accel += "<Control>"
                        if (e.modifiers & Qt.AltModifier) accel += "<Alt>"
                        if (e.modifiers & Qt.ShiftModifier) accel += "<Shift>"
                        if (e.modifiers & Qt.MetaModifier) accel += "<Super>"
                        var fkey = name.length > 1 && name[0] === "F" && !isNaN(name.slice(1))
                        if (name === "" || (accel === "" && !fkey)) {
                            message = theme.t("Use a modifier (Super, Ctrl, Alt) with a key.")
                            recording = false
                            return
                        }
                        recording = false
                        var err = backend.setHotkey(accel + name)
                        message = err === "" ? theme.t("Shortcut saved") : err
                    }
                }

                Column {
                    visible: !backend.hotkeySupported
                    width: parent.width
                    spacing: 6
                    Text {
                        text: theme.t("Not supported on this desktop") + " (" + backend.desktop + ")"
                        color: theme.danger
                        font.pixelSize: 12
                    }
                }

                Btn {
                    visible: backend.hotkey !== ""
                    text: theme.t("Remove shortcut")
                    danger: true
                    onClicked: backend.removeHotkey()
                }
            }
        }
    }

    // ====================================================================== Integrations
    Component {
        id: integrationsPage
        Column {
            spacing: 18
            PageTitle { text: theme.t("Integrations") }
            SetCard {
                SetRow {
                    label: theme.t("Background daemon")
                    hint: theme.t("Opens the wheel instantly and keeps the edge dock at login")
                          + " · " + (backend.daemonRunning ? theme.t("Running") : theme.t("Stopped"))
                    Toggle {
                        objectName: "daemonToggle"
                        checked: backend.autostart && backend.daemonRunning
                        onToggled: (on) => backend.setDaemon(on)
                    }
                }
                SetRow {
                    label: theme.t("File manager menus")
                    hint: theme.t("Right-click actions in Nautilus, Thunar, Dolphin and Nemo")
                    Toggle {
                        objectName: "menusToggle"
                        checked: backend.menusInstalled
                        onToggled: (on) => backend.setMenus(on)
                    }
                }
                Column {
                    visible: backend.menusInstalled
                    width: parent.width
                    spacing: 8
                    Text { text: theme.t("Quick actions in the menu"); color: theme.textDim; font.pixelSize: 12 }
                    Flow {
                        width: parent.width
                        spacing: 8
                        Repeater {
                            model: backend.quickChoices
                            delegate: Rectangle {
                                required property var modelData
                                readonly property bool on: backend.quickActions.length === 0
                                                           || backend.quickActions.indexOf(modelData.id) >= 0
                                width: qText.implicitWidth + 26
                                height: 30
                                radius: 15
                                color: on ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.16) : "transparent"
                                border.color: on ? theme.accent : theme.cardEdge
                                Text {
                                    id: qText
                                    anchors.centerIn: parent
                                    text: (parent.on ? "✓ " : "") + modelData.label
                                    color: theme.text
                                    font.pixelSize: 12
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        var all = backend.quickChoices.map(function (q) { return q.id })
                                        var cur = backend.quickActions.length ? backend.quickActions.slice() : all
                                        var i = cur.indexOf(parent.modelData.id)
                                        if (i >= 0) cur.splice(i, 1); else cur.push(parent.modelData.id)
                                        if (cur.length === 0 || cur.length === all.length) cur = []
                                        backend.set("quickActions", cur)
                                    }
                                }
                            }
                        }
                    }
                }
                SetRow {
                    label: theme.t("Edge dock")
                    hint: backend.dockSide === "left" ? theme.t("Docked on the left edge")
                        : backend.dockSide === "right" ? theme.t("Docked on the right edge")
                        : theme.t("Not docked: drag the wheel to a screen edge")
                    Btn {
                        visible: backend.dockSide !== ""
                        text: theme.t("Undock")
                        onClicked: backend.undock()
                    }
                }
                SetRow {
                    label: theme.t("Shell completion") + " (" + backend.shell + ")"
                    Btn {
                        text: backend.completionsInstalled ? theme.t("Installed") : theme.t("Install")
                        enabled: !backend.completionsInstalled
                        onClicked: backend.installCompletions()
                    }
                }
            }
        }
    }

    // ===================================================================== Watch folders
    Component {
        id: watchPage
        Column {
            spacing: 18
            PageTitle { text: theme.t("Watch folders") }
            SetCard {
                subtitle: theme.t("New files in these folders are converted automatically.")
                Text {
                    visible: backend.watchServices.length === 0
                    text: theme.t("No watched folders yet")
                    color: theme.textDim
                    font.pixelSize: 13
                }
                Repeater {
                    model: backend.watchServices
                    delegate: SetRow {
                        required property var modelData
                        label: modelData.desc
                        hint: modelData.name
                        Row {
                            spacing: 10
                            Pill {
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.active ? theme.t("Active") : theme.t("Inactive")
                                good: modelData.active
                            }
                            Btn {
                                text: theme.t("Remove")
                                danger: true
                                onClicked: backend.removeWatch(modelData.name)
                            }
                        }
                    }
                }
            }
            SetCard {
                id: addCard
                title: theme.t("Add a folder")
                property string folder: ""
                property string message: ""
                FolderDialog {
                    id: watchDialog
                    onAccepted: addCard.folder = selectedFolder.toString().replace("file://", "")
                }
                SetRow {
                    label: theme.t("Folder")
                    hint: addCard.folder
                    Btn { text: theme.t("Choose folder…"); onClicked: watchDialog.open() }
                }
                SetRow {
                    label: theme.t("Convert to")
                    QC.ComboBox {
                        id: targetBox
                        width: 160
                        model: backend.watchTargets
                        palette.button: theme.window
                        palette.buttonText: theme.text
                        palette.window: theme.card
                        palette.text: theme.text
                        palette.base: theme.window
                        palette.highlight: theme.accent
                    }
                }
                SetRow {
                    label: theme.t("Only these formats (optional)")
                    QC.TextField {
                        id: sourcesField
                        width: 200
                        placeholderText: "heic, png"
                        color: theme.text
                        placeholderTextColor: theme.textDim
                        background: Rectangle { radius: 10; color: theme.window; border.color: theme.cardEdge }
                    }
                }
                Row {
                    spacing: 14
                    Btn {
                        text: theme.t("Start watching")
                        primary: true
                        enabled: addCard.folder !== ""
                        onClicked: {
                            var err = backend.addWatch(addCard.folder, targetBox.currentText, sourcesField.text)
                            addCard.message = err
                            if (err === "") { addCard.folder = ""; sourcesField.text = "" }
                        }
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: addCard.message
                        color: theme.danger
                        font.pixelSize: 12
                    }
                }
            }
        }
    }

    // ============================================================================= Tools
    Component {
        id: toolsPage
        Column {
            spacing: 18
            Row {
                width: parent.width
                spacing: 16
                PageTitle { text: theme.t("Tools") }
                Btn { anchors.verticalCenter: parent.verticalCenter; text: theme.t("Refresh"); onClicked: backend.refresh() }
            }
            Text {
                text: theme.t("%1 of %2 conversions available", backend.conversionsNow, backend.conversionsAll)
                color: theme.accent
                font.pixelSize: 14
                font.bold: true
            }
            Repeater {
                model: backend.backends
                delegate: SetCard {
                    required property var modelData
                    SetRow {
                        label: modelData.name
                        hint: modelData.description
                        Pill {
                            text: modelData.ready ? theme.t("Ready") : theme.t("Missing")
                            good: modelData.ready
                        }
                    }
                    Repeater {
                        model: modelData.missing.concat(modelData.extras.filter(function (x) { return !x.present }))
                        delegate: SetRow {
                            required property var modelData
                            label: modelData.name + (modelData.purpose ? " · " + modelData.purpose : "")
                            hint: modelData.install
                            Btn {
                                property bool done: false
                                text: done ? theme.t("Copied") : theme.t("Copy install command")
                                onClicked: { backend.copy(modelData.install); done = true }
                            }
                        }
                    }
                }
            }
        }
    }

    // ============================================================================= About
    Component {
        id: aboutPage
        Column {
            spacing: 18
            PageTitle { text: theme.t("About") }
            SetCard {
                Row {
                    spacing: 20
                    Image {
                        source: "../icons/dotmorph.svg"
                        sourceSize: Qt.size(96, 96)
                        width: 96
                        height: 96
                    }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6
                        Text { text: "DotMorph"; color: theme.text; font.pixelSize: 26; font.bold: true }
                        Text { text: theme.t("Radial-menu file converter for Linux"); color: theme.textDim; font.pixelSize: 13 }
                        Text { text: theme.t("Version %1", backend.version); color: theme.accent; font.pixelSize: 13; font.bold: true }
                    }
                }
                Text {
                    width: parent.width
                    text: theme.t("Free and open source under Apache 2.0. No telemetry, nothing leaves your computer.")
                    color: theme.textDim
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                }
                Flow {
                    width: parent.width
                    spacing: 10
                    Btn { text: theme.t("Website"); primary: true; onClicked: win.open("https://dotsuite.dev/en/product/dotmorph") }
                    Btn { text: "DotSuite"; onClicked: win.open("https://dotsuite.dev/en") }
                    Btn { text: theme.t("Changelog"); onClicked: win.open("https://github.com/kareem2099/DotMorph/blob/main/CHANGELOG.md") }
                    Btn { text: theme.t("Source code"); onClicked: win.open("https://github.com/kareem2099/DotMorph") }
                }
            }
            SetCard {
                title: theme.t("Part of DotSuite")
                Text {
                    text: "DOT<font color='" + theme.text + "'>SUITE</font>"
                    textFormat: Text.StyledText
                    color: theme.accent
                    font.pixelSize: 28
                    font.bold: true
                    font.letterSpacing: 4
                }
                SetRow {
                    label: theme.t("Settings file")
                    hint: backend.settingsPath
                    Btn { text: "↗"; onClicked: backend.openSettingsFile() }
                }
            }
        }
    }
}
