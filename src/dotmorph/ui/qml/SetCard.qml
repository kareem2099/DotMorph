import QtQuick

// A titled card on a settings page. Children go into a column.
Rectangle {
    id: card

    property string title: ""
    property string subtitle: ""
    default property alias content: body.data

    width: parent ? parent.width : 400
    implicitHeight: column.implicitHeight + 36
    height: implicitHeight
    radius: 16
    color: theme.card
    border.width: 1
    border.color: theme.cardEdge

    Column {
        id: column
        x: 20
        y: 18
        width: card.width - 40
        spacing: 14

        Column {
            width: parent.width
            spacing: 4
            visible: card.title !== ""
            Text {
                width: parent.width
                text: card.title
                color: theme.text
                font.pixelSize: 15
                font.bold: true
            }
            Text {
                width: parent.width
                visible: card.subtitle !== ""
                text: card.subtitle
                color: theme.textDim
                font.pixelSize: 12
                wrapMode: Text.Wrap
            }
        }

        Column {
            id: body
            width: parent.width
            spacing: 14
        }
    }
}
