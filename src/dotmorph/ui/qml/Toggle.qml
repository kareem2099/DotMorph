import QtQuick

// On/off switch. `checked` is driven from outside; clicking emits toggled(!checked).
Rectangle {
    id: sw

    property bool checked: false
    property bool busy: false
    signal toggled(bool on)

    width: 48
    height: 28
    radius: 14
    opacity: busy ? 0.5 : 1
    color: checked ? theme.accent : Qt.rgba(0.5, 0.5, 0.5, 0.25)
    Behavior on color { ColorAnimation { duration: theme.ms(140) } }

    Rectangle {
        width: 22
        height: 22
        radius: 11
        anchors.verticalCenter: parent.verticalCenter
        // the knob moves toward the reading direction's end
        x: (sw.checked !== theme.rtl) ? parent.width - width - 3 : 3
        color: "white"
        Behavior on x { NumberAnimation { duration: theme.ms(160); easing.type: Easing.OutCubic } }
    }

    MouseArea {
        anchors.fill: parent
        enabled: !sw.busy
        cursorShape: Qt.PointingHandCursor
        onClicked: sw.toggled(!sw.checked)
    }
}
