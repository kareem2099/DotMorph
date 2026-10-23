import QtQuick

// Conversion options for the wheel: quality, render resolution, resize, metadata.
// Values live in the bridge and are remembered between runs.
Rectangle {
    id: panel

    required property Theme theme
    property bool open: false
    signal closed()

    width: 330
    height: column.implicitHeight + 36
    radius: 22
    color: theme.hub
    border.width: 1
    border.color: theme.backdropEdge

    LayoutMirroring.enabled: theme.rtl
    LayoutMirroring.childrenInherit: true

    visible: opacity > 0
    opacity: open ? 1 : 0
    scale: open ? 1 : 0.85
    Behavior on opacity { NumberAnimation { duration: panel.theme.ms(160) } }
    Behavior on scale { NumberAnimation { duration: panel.theme.ms(220); easing.type: Easing.OutBack } }

    // swallow clicks so the wheel underneath doesn't react
    MouseArea { anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.AllButtons }

    // ---- small building blocks --------------------------------------------------------
    component Label: Text {
        color: panel.theme.textDim
        font.pixelSize: 11
        font.bold: true
        font.letterSpacing: 1
    }

    component Segmented: Row {
        id: seg
        property var options: []       // [{value, text}]
        property var current
        signal chosen(var value)
        spacing: 4
        Repeater {
            model: seg.options
            delegate: Rectangle {
                required property var modelData
                readonly property bool on: modelData.value === seg.current
                width: Math.max(44, t.implicitWidth + 18)
                height: 28
                radius: 14
                color: on ? panel.theme.accent : (hit.containsMouse ? Qt.rgba(1, 1, 1, 0.10) : Qt.rgba(1, 1, 1, 0.05))
                border.color: on ? Qt.lighter(panel.theme.accent, 1.3) : panel.theme.backdropEdge
                Behavior on color { ColorAnimation { duration: panel.theme.ms(120) } }
                Text {
                    id: t
                    anchors.centerIn: parent
                    text: modelData.text
                    color: parent.on ? "white" : panel.theme.text
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

    Column {
        id: column
        x: 20
        y: 18
        width: panel.width - 40
        spacing: 12

        Item {
            width: parent.width
            height: 22
            Text {
                anchors.left: parent.left  // anchors flip with right-to-left text; x doesn't
                text: panel.theme.t("Options")
                color: panel.theme.text
                font.pixelSize: 16
                font.bold: true
            }
            Text {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: panel.theme.t("Reset")
                color: resetHit.containsMouse ? panel.theme.accentHot : panel.theme.textDim
                font.pixelSize: 12
                MouseArea {
                    id: resetHit
                    anchors.fill: parent
                    anchors.margins: -6
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: bridge.resetOptions()
                }
            }
        }

        // quality slider
        Column {
            width: parent.width
            spacing: 6
            Item {
                width: parent.width
                height: 14
                Label { anchors.left: parent.left; text: panel.theme.t("QUALITY  (JPG / WEBP / AVIF)") }
                Text {
                    anchors.right: parent.right
                    text: bridge.quality
                    color: panel.theme.text
                    font.pixelSize: 12
                    font.bold: true
                }
            }
            Item {
                id: slider
                objectName: "qualitySlider"
                width: parent.width
                height: 24
                readonly property real minV: 10
                readonly property real maxV: 100
                readonly property real frac: (bridge.quality - minV) / (maxV - minV)
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width
                    height: 6
                    radius: 3
                    color: Qt.rgba(1, 1, 1, panel.theme.light ? 0.0 : 0.08)
                    border.color: panel.theme.backdropEdge
                    Rectangle {
                        anchors.left: parent.left
                        width: parent.width * slider.frac
                        height: parent.height
                        radius: 3
                        color: panel.theme.accent
                    }
                }
                Rectangle {
                    x: (panel.theme.rtl ? 1 - slider.frac : slider.frac) * (slider.width - width)
                    anchors.verticalCenter: parent.verticalCenter
                    width: 18
                    height: 18
                    radius: 9
                    color: "white"
                    border.color: panel.theme.accent
                    border.width: 2
                    scale: drag.pressed ? 1.2 : 1
                    Behavior on scale { NumberAnimation { duration: panel.theme.ms(100) } }
                }
                MouseArea {
                    id: drag
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    function set(mx) {
                        var f = Math.max(0, Math.min(1, mx / slider.width))
                        if (panel.theme.rtl) f = 1 - f
                        var v = Math.round((slider.minV + f * (slider.maxV - slider.minV)) / 5) * 5
                        if (v !== bridge.quality) bridge.setOption("quality", v)
                    }
                    onPressed: (m) => set(m.x)
                    onPositionChanged: (m) => { if (pressed) set(m.x) }
                }
            }
        }

        // render resolution, only when it matters (PDF, SVG, ...)
        Column {
            visible: bridge.usesDpi
            width: parent.width
            spacing: 6
            Label { text: panel.theme.t("RESOLUTION  (PDF / SVG)") }
            Segmented {
                objectName: "dpiChoice"
                options: [{ value: 0, text: panel.theme.t("Auto") }, { value: 72, text: "72" },
                          { value: 150, text: "150" }, { value: 300, text: "300 dpi" }]
                current: bridge.dpi
                onChosen: (v) => bridge.setOption("dpi", v)
            }
        }

        Column {
            width: parent.width
            spacing: 6
            Label { text: panel.theme.t("SIZE") }
            Segmented {
                objectName: "resizeChoice"
                options: [{ value: "", text: panel.theme.t("Original") }, { value: "75%", text: "75%" },
                          { value: "50%", text: "50%" }, { value: "25%", text: "25%" }]
                current: bridge.resize
                onChosen: (v) => bridge.setOption("resize", v)
            }
        }

        // strip metadata toggle
        Item {
            width: parent.width
            height: 28
            Column {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                Text { text: panel.theme.t("Remove metadata"); color: panel.theme.text; font.pixelSize: 13 }
                Text { text: panel.theme.t("EXIF, GPS, tags"); color: panel.theme.textDim; font.pixelSize: 10 }
            }
            Rectangle {
                objectName: "stripToggle"
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                width: 46
                height: 26
                radius: 13
                color: bridge.strip ? panel.theme.success : Qt.rgba(1, 1, 1, 0.10)
                border.color: panel.theme.backdropEdge
                Behavior on color { ColorAnimation { duration: panel.theme.ms(140) } }
                Rectangle {
                    x: (bridge.strip !== panel.theme.rtl) ? parent.width - width - 3 : 3
                    anchors.verticalCenter: parent.verticalCenter
                    width: 20; height: 20; radius: 10
                    color: "white"
                    Behavior on x { NumberAnimation { duration: panel.theme.ms(160); easing.type: Easing.OutCubic } }
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: bridge.setOption("strip", !bridge.strip)
                }
            }
        }

        Rectangle {
            width: parent.width
            height: 34
            radius: 17
            color: doneHit.containsMouse ? Qt.lighter(panel.theme.accent, 1.15) : panel.theme.accent
            Text {
                anchors.centerIn: parent
                text: panel.theme.t("Done")
                color: "white"
                font.pixelSize: 13
                font.bold: true
            }
            MouseArea {
                id: doneHit
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: panel.closed()
            }
        }

        Text {
            objectName: "allSettings"
            anchors.horizontalCenter: parent.horizontalCenter
            text: panel.theme.t("All settings…")
            color: settingsHit.containsMouse ? panel.theme.accentHot : panel.theme.textDim
            font.pixelSize: 12
            font.underline: settingsHit.containsMouse
            MouseArea {
                id: settingsHit
                anchors.fill: parent
                anchors.margins: -6
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: { bridge.openSettings(); panel.closed() }
            }
        }
    }
}
