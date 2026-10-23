import QtQuick
import QtQuick.Window

// The docked wheel: a slim glowing tab glued to a screen edge.
//   hover (a moment) or click -> open the half wheel     drag files over it -> opens too
//   drag up/down -> slide along the edge                 drag away from the edge -> full wheel
//   right-click -> hide / quit
Item {
    id: tab

    required property Theme theme
    property string side: "left"
    readonly property bool onLeft: side === "left"
    readonly property real visibleW: 34

    // slide in from the edge whenever the tab appears
    property real enter: 0
    onVisibleChanged: if (visible) { enter = 0; enterAnim.restart() }
    Component.onCompleted: enterAnim.start()
    NumberAnimation {
        id: enterAnim; target: tab; property: "enter"; from: 0; to: 1
        duration: tab.theme.ms(320); easing.type: Easing.OutBack
    }

    Item {
        id: body
        width: parent.width
        height: parent.height
        x: (tab.onLeft ? -1 : 1) * (1 - tab.enter) * tab.visibleW

        Rectangle {
            id: pill
            readonly property real tuck: 22  // part hidden past the screen edge
            width: tab.visibleW + tuck
            height: parent.height - 12
            y: 6
            x: tab.onLeft ? -tuck : parent.width - tab.visibleW
            radius: 22
            color: tab.theme.hub
            border.width: 1.2
            border.color: area.containsMouse || area.dwell ? tab.theme.accent : tab.theme.backdropEdge
            Behavior on border.color { ColorAnimation { duration: tab.theme.ms(150) } }
        }

        // breathing light along the inner edge of the tab
        Rectangle {
            width: 3
            height: pill.height - 44
            radius: 1.5
            anchors.verticalCenter: pill.verticalCenter
            x: tab.onLeft ? tab.visibleW - 7 : tab.width - tab.visibleW + 4
            color: bridge.busy ? tab.theme.success : tab.theme.accent
            SequentialAnimation on opacity {
                running: tab.theme.motion > 0 && tab.visible
                loops: Animation.Infinite
                NumberAnimation { from: 0.35; to: 1; duration: 1400; easing.type: Easing.InOutSine }
                NumberAnimation { from: 1; to: 0.35; duration: 1400; easing.type: Easing.InOutSine }
            }
        }

        Image {
            source: "../icons/dotmorph.svg"
            sourceSize: Qt.size(26, 26)
            width: 26; height: 26
            x: tab.onLeft ? (tab.visibleW - width) / 2 - 2 : tab.width - tab.visibleW + (tab.visibleW - width) / 2 + 2
            anchors.verticalCenter: pill.verticalCenter
            scale: area.containsMouse ? 1.12 : 1
            Behavior on scale { NumberAnimation { duration: tab.theme.ms(160); easing.type: Easing.OutBack } }
        }

        // conversion still running while the wheel is folded: fill the tab bottom-up
        Rectangle {
            visible: bridge.busy
            width: 4
            radius: 2
            x: tab.onLeft ? 4 : tab.width - 8
            height: (pill.height - 30) * bridge.progress
            y: pill.y + pill.height - 15 - height
            color: tab.theme.success
            Behavior on height { NumberAnimation { duration: tab.theme.ms(250) } }
        }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        cursorShape: dragged ? Qt.ClosedHandCursor : Qt.PointingHandCursor
        property bool dwell: false
        property point pressAt: Qt.point(0, 0)
        property bool dragged: false

        Timer { id: dwellTimer; interval: 280; onTriggered: dock.peek() }
        onEntered: { dwell = true; dwellTimer.restart() }
        onExited: { dwell = false; dwellTimer.stop() }
        onPressed: (m) => { pressAt = Qt.point(m.x, m.y); dragged = false; dwellTimer.stop() }
        onPositionChanged: (m) => {
            if (!pressed) return
            var mx = m.x - pressAt.x, my = m.y - pressAt.y
            if (!dragged && mx * mx + my * my > 25) dragged = true
            if (!dragged) return
            var away = tab.onLeft ? mx : -mx
            if (away > 60) {  // pulled off the edge: become the full wheel again
                dock.undock()
                var w = tab.Window.window
                if (w) w.startSystemMove()
            } else {
                dock.slide(my)
            }
        }
        onReleased: if (dragged) dock.slideEnded()
        onClicked: (m) => {
            if (dragged) { dragged = false; return }
            if (m.button === Qt.RightButton) dock.dismiss()
            else dock.peek()
        }
    }
}
