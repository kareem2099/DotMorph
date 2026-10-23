import QtQuick
import QtQuick.Shapes

// The centre of the wheel: file name / hovered target, then a progress arc while
// converting, then a self-drawing check mark (or a cross) when done.
Item {
    id: hub

    required property Theme theme
    property real r: 62
    property string title: ""
    property string subtitle: ""
    property color tint: theme.accent
    property string mode: "idle"      // idle | busy | done | failed
    property real progress: 0
    property bool cancelHint: false

    width: r * 2
    height: r * 2

    // seconds since the job started: shown when the tool can't report progress
    // (e.g. ffmpeg's GIF palette pass reads the whole video before writing anything)
    property int elapsed: 0
    onModeChanged: elapsed = 0
    Timer {
        interval: 1000
        repeat: true
        running: hub.mode === "busy"
        onTriggered: hub.elapsed += 1
    }
    readonly property bool known: progress >= 0.01

    // displayed progress glides instead of jumping
    property real shown: mode === "busy" ? progress : (mode === "done" ? 1 : 0)
    Behavior on shown { NumberAnimation { duration: hub.theme.ms(280); easing.type: Easing.OutCubic } }

    property real flash: 0
    function pulse() { flashAnim.restart() }
    SequentialAnimation {
        id: flashAnim
        NumberAnimation { target: hub; property: "flash"; to: 1; duration: hub.theme.ms(90) }
        NumberAnimation { target: hub; property: "flash"; to: 0; duration: hub.theme.ms(600); easing.type: Easing.OutQuad }
    }

    readonly property color stateColor: mode === "done" ? theme.success
                                      : mode === "failed" ? theme.danger : tint

    // soft halo behind the disc
    Rectangle {
        anchors.centerIn: parent
        width: hub.r * 2 + 18 + 26 * hub.flash
        height: width
        radius: width / 2
        color: "transparent"
        border.width: 6
        border.color: Qt.rgba(hub.stateColor.r, hub.stateColor.g, hub.stateColor.b, 0.18 + 0.5 * hub.flash)
    }

    Rectangle {
        id: disc
        anchors.centerIn: parent
        width: hub.r * 2
        height: width
        radius: width / 2
        color: hub.theme.hub
        border.width: 1.5
        border.color: Qt.rgba(hub.stateColor.r, hub.stateColor.g, hub.stateColor.b, 0.55)
        Behavior on border.color { ColorAnimation { duration: hub.theme.ms(200) } }
    }

    // progress track + arc
    Shape {
        anchors.fill: parent
        visible: hub.mode !== "idle"
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: Qt.rgba(1, 1, 1, hub.theme.light ? 0.0 : 0.07)
            strokeWidth: 5
            fillColor: "transparent"
            PathAngleArc { centerX: hub.r; centerY: hub.r; radiusX: hub.r - 6; radiusY: hub.r - 6; startAngle: 0; sweepAngle: 360 }
        }
        ShapePath {
            strokeColor: hub.stateColor
            strokeWidth: 5
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            PathAngleArc {
                centerX: hub.r; centerY: hub.r; radiusX: hub.r - 6; radiusY: hub.r - 6
                startAngle: -90; sweepAngle: 360 * hub.shown
            }
        }
    }

    // spinner while we wait for the first progress report
    Shape {
        id: spinner
        anchors.fill: parent
        visible: hub.mode === "busy" && hub.progress < 0.01
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: hub.tint
            strokeWidth: 5
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            PathAngleArc { centerX: hub.r; centerY: hub.r; radiusX: hub.r - 6; radiusY: hub.r - 6; startAngle: 0; sweepAngle: 70 }
        }
        RotationAnimation on rotation {
            running: spinner.visible && hub.theme.motion > 0
            from: 0; to: 360; duration: 900; loops: Animation.Infinite
        }
    }

    // orbiting spark at the head of the arc
    Rectangle {
        visible: hub.mode === "busy" && hub.shown > 0.01
        readonly property real a: (-90 + 360 * hub.shown) * Math.PI / 180
        x: hub.r + (hub.r - 6) * Math.cos(a) - width / 2
        y: hub.r + (hub.r - 6) * Math.sin(a) - height / 2
        width: 11; height: 11; radius: 5.5
        color: Qt.lighter(hub.tint, 1.5)
        Rectangle {
            anchors.centerIn: parent
            width: 22; height: 22; radius: 11
            color: Qt.rgba(hub.tint.r, hub.tint.g, hub.tint.b, 0.3)
        }
    }

    // check mark / cross, drawn stroke by stroke
    Canvas {
        id: mark
        anchors.centerIn: parent
        width: hub.r; height: hub.r
        property real t: 0
        visible: hub.mode === "done" || hub.mode === "failed"
        onTChanged: requestPaint()
        onVisibleChanged: if (visible) { t = 0; markAnim.restart() }
        NumberAnimation {
            id: markAnim; target: mark; property: "t"; from: 0; to: 1
            duration: hub.theme.ms(420); easing.type: Easing.OutCubic
        }
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.lineWidth = 5
            ctx.lineCap = "round"
            ctx.lineJoin = "round"
            ctx.strokeStyle = hub.stateColor
            var w = width, h = height
            var segs = hub.mode === "done"
                ? [[[0.22, 0.52], [0.42, 0.72]], [[0.42, 0.72], [0.80, 0.30]]]
                : [[[0.28, 0.28], [0.72, 0.72]], [[0.72, 0.28], [0.28, 0.72]]]
            var lens = segs.map(function (s) { return Math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]) })
            var total = lens[0] + lens[1], left = (hub.theme.motion > 0 ? t : 1) * total
            ctx.beginPath()
            for (var i = 0; i < 2 && left > 0; i++) {
                var f = Math.min(1, left / lens[i]), s = segs[i]
                if (hub.mode === "failed" || i === 0) ctx.moveTo(s[0][0] * w, s[0][1] * h)
                ctx.lineTo((s[0][0] + (s[1][0] - s[0][0]) * f) * w, (s[0][1] + (s[1][1] - s[0][1]) * f) * h)
                left -= lens[i]
            }
            ctx.stroke()
        }
    }

    Column {
        anchors.centerIn: parent
        width: hub.r * 1.55
        spacing: 1
        visible: hub.mode === "idle" || hub.mode === "busy"

        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: hub.mode === "busy" ? (hub.cancelHint ? hub.theme.t("Cancel")
                                         : hub.known ? Math.round(hub.progress * 100) + "%"
                                         : hub.elapsed + "s")
                                      : hub.title
            color: hub.mode === "busy" && hub.cancelHint ? hub.theme.danger : hub.theme.text
            font.pixelSize: hub.mode === "busy" ? 22 : (hub.title.length > 14 ? 12 : 15)
            font.bold: true
            elide: Text.ElideMiddle
            wrapMode: hub.mode === "busy" ? Text.NoWrap : Text.Wrap
            maximumLineCount: 2
        }
        Text {
            width: parent.width
            visible: text !== ""
            horizontalAlignment: Text.AlignHCenter
            text: hub.mode === "busy" ? (hub.cancelHint ? hub.theme.t("click") : hub.theme.t("converting")) : hub.subtitle
            color: hub.theme.textDim
            font.pixelSize: 10
            elide: Text.ElideRight
        }
    }
}
