import QtQuick

// Segmented choice: options [{value, text}], highlights `current`, emits chosen(value).
Row {
    id: seg

    property var options: []
    property var current
    signal chosen(var value)

    spacing: 4

    Repeater {
        model: seg.options
        delegate: Rectangle {
            required property var modelData
            readonly property bool on: modelData.value === seg.current
            width: Math.max(52, label.implicitWidth + 22)
            height: 32
            radius: 16
            color: on ? theme.accent : (hit.containsMouse ? Qt.rgba(0.5, 0.5, 0.5, 0.16) : Qt.rgba(0.5, 0.5, 0.5, 0.08))
            border.color: on ? Qt.lighter(theme.accent, 1.2) : theme.cardEdge
            Behavior on color { ColorAnimation { duration: theme.ms(120) } }
            Text {
                id: label
                anchors.centerIn: parent
                text: modelData.text
                color: parent.on ? "#0A0A0A" : theme.text
                font.pixelSize: 12
                font.bold: parent.on
            }
            MouseArea {
                id: hit
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: seg.chosen(parent.modelData.value)
            }
        }
    }
}
