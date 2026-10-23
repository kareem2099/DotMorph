import QtQuick
import QtQuick.Layouts

// One setting: label (+ hint) on one side, its control on the other.
Item {
    id: row

    property string label: ""
    property string hint: ""
    default property alias control: slot.data

    width: parent ? parent.width : 400
    implicitHeight: Math.max(texts.implicitHeight, slot.childrenRect.height)
    height: implicitHeight

    RowLayout {
        anchors.fill: parent
        spacing: 16

        Column {
            id: texts
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: 2
            Text {
                width: parent.width
                text: row.label
                color: theme.text
                font.pixelSize: 13
                wrapMode: Text.Wrap
            }
            Text {
                width: parent.width
                visible: row.hint !== ""
                text: row.hint
                color: theme.textDim
                font.pixelSize: 11
                wrapMode: Text.Wrap
            }
        }

        Item {
            id: slot
            Layout.alignment: Qt.AlignVCenter
            implicitWidth: childrenRect.width
            implicitHeight: childrenRect.height
        }
    }
}
