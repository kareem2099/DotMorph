import QtQuick

// Horizontal slider with a value badge. Emits moved(value) while dragging.
Item {
    id: slider

    property real from: 10
    property real to: 100
    property real step: 5
    property real value: 90
    signal moved(real value)

    width: 260
    height: 28
    readonly property real frac: (value - from) / (to - from)

    Rectangle {
        id: track
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width - 46
        height: 6
        radius: 3
        color: Qt.rgba(0.5, 0.5, 0.5, 0.22)
        Rectangle {
            width: parent.width * slider.frac
            height: parent.height
            radius: 3
            color: theme.accent
            anchors.left: parent.left
        }
        Rectangle {
            x: (theme.rtl ? 1 - slider.frac : slider.frac) * (track.width - width)
            anchors.verticalCenter: parent.verticalCenter
            width: 18
            height: 18
            radius: 9
            color: "white"
            border.color: theme.accent
            border.width: 2
        }
        MouseArea {
            anchors.fill: parent
            anchors.margins: -10
            cursorShape: Qt.PointingHandCursor
            function set(mx) {
                var f = Math.max(0, Math.min(1, (mx - 10) / track.width))
                if (theme.rtl) f = 1 - f
                var v = Math.round((slider.from + f * (slider.to - slider.from)) / slider.step) * slider.step
                if (v !== slider.value) slider.moved(v)
            }
            onPressed: (m) => set(m.x)
            onPositionChanged: (m) => { if (pressed) set(m.x) }
        }
    }
    Text {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: Math.round(slider.value)
        color: theme.text
        font.pixelSize: 13
        font.bold: true
    }
}
