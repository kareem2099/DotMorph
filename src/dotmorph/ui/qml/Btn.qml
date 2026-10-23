import QtQuick

// Button: primary (emerald), plain, or danger.
Rectangle {
    id: btn

    property string text: ""
    property bool primary: false
    property bool danger: false
    signal clicked()

    width: label.implicitWidth + 30
    height: 34
    radius: 17
    opacity: enabled ? 1 : 0.45
    readonly property color base: primary ? theme.accent : danger ? theme.danger : Qt.rgba(0.5, 0.5, 0.5, 0.12)
    color: hit.containsMouse && enabled ? Qt.lighter(base, primary || danger ? 1.12 : 1.6) : base
    border.color: primary || danger ? "transparent" : theme.cardEdge
    Behavior on color { ColorAnimation { duration: theme.ms(120) } }

    Text {
        id: label
        anchors.centerIn: parent
        text: btn.text
        color: btn.primary ? "#0A0A0A" : btn.danger ? "white" : theme.text
        font.pixelSize: 12
        font.bold: btn.primary
    }
    MouseArea {
        id: hit
        anchors.fill: parent
        hoverEnabled: true
        enabled: btn.enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: btn.clicked()
    }
}
