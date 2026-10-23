import QtQuick
import QtQuick.Window

// Frameless, transparent, always-on-top window that hosts the radial menu.
Window {
    id: win
    width: 560
    height: 560
    visible: !bridge.persistent  // the daemon shows it on request
    color: "transparent"
    title: "DotMorph"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool

    Theme {
        id: theme
        name: bridge.theme
        reduceMotion: bridge.reduceMotion
    }

    // Edge dock (see dock.py): "free" wheel, "docked" tab, or "peek" half wheel.
    readonly property bool docked: dock.mode === "docked"
    readonly property bool peeking: dock.mode === "peek"
    onPeekingChanged: {
        if (!peeking) return
        closing = false
        if (wheel.phase !== "busy") wheel.phase = "idle"
        wheel.hoverInner = -1
        wheel.hoverOuter = -1
        stage.rotation = 0
        stage.scale = 0.7
        stage.opacity = 0
        wheel.forceActiveFocus()
        openAnim.restart()
    }

    // Implode into the centre, then quit (or hide, in the daemon).
    // Docked: fold back into the edge tab instead.
    property bool closing: false
    function close() {
        if (closing) return
        closing = true
        closeTimer.stop()
        if (dock.mode !== "free") {
            wheel.optionsOpen = false
            if (theme.motion === 0) { dock.collapse(); closing = false; return }
            fold.start()
            return
        }
        if (theme.motion === 0) { finishClose(); return }
        implode.start()
    }
    function finishClose() {
        if (!bridge.persistent) { Qt.quit(); return }
        win.hide()
        bridge.menuHidden()
    }
    // Daemon: pop up again with the open animation.
    function reopen() {
        implode.stop()
        closeTimer.stop()
        closing = false
        stage.rotation = 0
        stage.scale = 0.7
        stage.opacity = 0
        if (dock.mode === "docked") dock.peek()
        win.show()
        win.raise()
        win.requestActivate()
        wheel.forceActiveFocus()
        openAnim.restart()
    }

    // a point on the rim of the wheel's disc, angle in degrees from 12 o'clock clockwise
    function rimR() { return win.peeking ? wheel.outerB + 30 : Math.min(win.width, win.height) / 2 - 34 }
    function rimX(angle) { return wheel.cx + rimR() * Math.sin(angle * Math.PI / 180) }
    function rimY(angle) { return wheel.cy - rimR() * Math.cos(angle * Math.PI / 180) }

    Shortcut {
        sequence: "Escape"
        onActivated: wheel.optionsOpen ? wheel.optionsOpen = false : win.close()
    }

    Connections {
        target: bridge
        function onFinished(ok) {
            if (ok) wheel.celebrate(); else wheel.fail()
            closeTimer.interval = ok ? 1600 : 4000
            closeTimer.restart()
        }
        function onSectorsChanged() { closeTimer.stop() }
        function onCancelled() { wheel.phase = "idle" }
        function onSummoned() { win.reopen() }
    }
    Timer { id: closeTimer; onTriggered: win.close() }

    // Half wheel open but the pointer left (and nothing is going on): fold it back.
    HoverHandler { id: hover }
    Timer {
        id: autoFold
        interval: 700
        running: win.peeking && !hover.hovered && !dropArea.containsDrag && !wheel.optionsOpen
                 && wheel.phase === "idle" && !wheel.moving && !win.closing
        onTriggered: win.close()
    }

    EdgeTab {
        id: edgeTab
        objectName: "edgeTab"
        anchors.fill: parent
        theme: theme
        side: dock.side
        visible: win.docked
    }

    Item {
        id: stage
        anchors.fill: parent
        visible: !win.docked
        transformOrigin: win.peeking ? (dock.side === "left" ? Item.Left : Item.Right) : Item.Center
        scale: 0.7
        opacity: 0

        Component.onCompleted: openAnim.start()
        ParallelAnimation {
            id: openAnim
            NumberAnimation { target: stage; property: "scale"; to: 1; duration: theme.ms(380); easing.type: Easing.OutBack; easing.overshoot: 1.4 }
            NumberAnimation { target: stage; property: "opacity"; to: 1; duration: theme.ms(200) }
        }
        SequentialAnimation {
            id: implode
            ParallelAnimation {
                NumberAnimation { target: stage; property: "scale"; to: 0.15; duration: 260; easing.type: Easing.InBack; easing.overshoot: 1.6 }
                NumberAnimation { target: stage; property: "rotation"; to: -35; duration: 260; easing.type: Easing.InQuad }
                NumberAnimation { target: stage; property: "opacity"; to: 0; duration: 260; easing.type: Easing.InQuad }
            }
            ScriptAction { script: win.finishClose() }
        }
        SequentialAnimation {
            id: fold
            ParallelAnimation {
                NumberAnimation { target: stage; property: "scale"; to: 0.45; duration: 200; easing.type: Easing.InCubic }
                NumberAnimation { target: stage; property: "opacity"; to: 0; duration: 200 }
            }
            ScriptAction { script: { dock.collapse(); win.closing = false } }
        }

        Wheel {
            id: wheel
            objectName: "wheel"
            anchors.fill: parent
            theme: theme
            half: win.peeking
            side: dock.side
            isDragging: dropArea.containsDrag
            onPicked: (target) => bridge.convertTo(target)
            onDismissed: win.close()
        }

        // options button, on the rim at 7:30
        Rectangle {
            id: optionsBtn
            objectName: "optionsButton"
            width: 32; height: 32; radius: 16
            // 7:30 on the full wheel; on a half wheel, low on its open side
            readonly property real angle: win.peeking ? (dock.side === "left" ? 140 : 220) : 225
            x: win.rimX(angle) - width / 2
            y: win.rimY(angle) - height / 2
            visible: bridge.hasFiles && wheel.phase !== "busy"
            color: optArea.containsMouse || wheel.optionsOpen ? theme.accent : theme.hub
            border.color: theme.backdropEdge
            scale: optArea.containsMouse ? 1.12 : 1
            Behavior on scale { NumberAnimation { duration: theme.ms(140); easing.type: Easing.OutBack } }
            Behavior on color { ColorAnimation { duration: theme.ms(140) } }
            z: 20
            CategoryIcon {
                anchors.centerIn: parent
                width: 18; height: 18
                category: "options"
                color: optArea.containsMouse || wheel.optionsOpen ? "white" : theme.textDim
            }
            // dot when options differ from the defaults
            Rectangle {
                visible: bridge.optionsSummary !== ""
                width: 9; height: 9; radius: 4.5
                anchors.right: parent.right; anchors.top: parent.top
                color: theme.success
            }
            MouseArea {
                id: optArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: wheel.optionsOpen = !wheel.optionsOpen
            }
        }

        // close button, sitting on the rim at 1:30
        Rectangle {
            id: closeBtn
            width: 28; height: 28; radius: 14
            readonly property real angle: win.peeking ? (dock.side === "left" ? 40 : 320) : 45
            x: win.rimX(angle) - width / 2
            y: win.rimY(angle) - height / 2
            color: closeArea.containsMouse ? theme.danger : theme.hub
            border.color: closeArea.containsMouse ? Qt.lighter(theme.danger, 1.3) : theme.backdropEdge
            scale: closeArea.containsMouse ? 1.12 : 1
            Behavior on scale { NumberAnimation { duration: theme.ms(140); easing.type: Easing.OutBack } }
            Behavior on color { ColorAnimation { duration: theme.ms(140) } }
            z: 20
            Text {
                anchors.centerIn: parent
                text: "✕"
                color: closeArea.containsMouse ? "white" : theme.textDim
                font.pixelSize: 12
                font.bold: true
            }
            MouseArea {
                id: closeArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: win.close()
            }
        }
    }

    // Dropping files onto the menu loads them.
    DropArea {
        id: dropArea
        anchors.fill: parent
        onEntered: (drag) => {
            if (drag.hasUrls || drag.hasText) drag.acceptProposedAction()
            if (win.docked) dock.peek()  // files dragged over the edge tab: open up
        }
        onPositionChanged: (drag) => {
            if (drag.hasUrls || drag.hasText) drag.acceptProposedAction()
        }
        onDropped: (drop) => {
            var items = []
            if (drop.hasUrls && drop.urls && drop.urls.length > 0) {
                for (var i = 0; i < drop.urls.length; i++) {
                    items.push(drop.urls[i].toString())
                }
            } else if (drop.hasText && drop.text) {
                items.push(drop.text)
            }
            if (items.length > 0) {
                drop.acceptProposedAction()
                bridge.setFilesFromUrls(items)
            }
        }
    }
}
