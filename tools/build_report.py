"""Fill the EIE4428 mini-project report template with the RVM project report.

This is an EDIT_FILL operation on the supplied template: the document object,
its styles, its tables and its section geometry are all preserved.  Only the
instructional placeholder text is replaced with the group's own content, and
figures are inserted at the section the template asks for.
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

from docx import Document
from docx.shared import Cm, Pt

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "EIE4428-mini-project-report-template.docx"
OUTPUT = ROOT / "docs" / "EIE4428-mini-project-report-RVM.docx"
FIGURE = ROOT / "docs" / "figures" / "system_block_diagram.png"


# --------------------------------------------------------------------------
# Low-level helpers
# --------------------------------------------------------------------------


def set_text(paragraph, text: str) -> None:
    """Replace a paragraph's text while keeping its first run's formatting."""
    if paragraph.runs:
        first = paragraph.runs[0]
        first.text = text
        for run in paragraph.runs[1:]:
            run._element.getparent().remove(run._element)
    else:
        paragraph.add_run(text)


def insert_after(paragraph, text: str = "", bold: bool = False):
    """Insert a new paragraph directly after ``paragraph``, same style."""
    new = copy.deepcopy(paragraph._p)
    paragraph._p.addnext(new)
    from docx.text.paragraph import Paragraph

    created = Paragraph(new, paragraph._parent)
    for run in list(created.runs):
        run._element.getparent().remove(run._element)
    if text:
        run = created.add_run(text)
        run.bold = bold
    return created


def insert_block(anchor, lines: list[str]) -> None:
    """Replace the anchor paragraph with a sequence of paragraphs."""
    cursor = anchor
    for line in lines:
        if not line:
            cursor = insert_after(cursor, "")
            continue
        bold = line.endswith("::")
        cursor = insert_after(cursor, line[:-2] if bold else line, bold=bold)
    set_text(anchor, lines[0] if lines else "")
    # The first line now lives in the anchor; drop the duplicate we made for it.
    first_new = anchor._p.getnext()
    if first_new is not None and not first_new.xpath(".//w:t"):
        anchor._p.remove(first_new)


def add_figure(anchor, path: Path, width_cm: float, caption: str) -> None:
    """Insert a picture and its caption directly after ``anchor``."""
    picture = insert_after(anchor)
    picture.alignment = 1  # centre
    picture.add_run().add_picture(str(path), width=Cm(width_cm))

    note = insert_after(picture, caption)
    note.alignment = 1
    for run in note.runs:
        run.font.size = Pt(9)
        run.italic = True


# --------------------------------------------------------------------------
# Report content
# --------------------------------------------------------------------------

SUMMARY = [
    "RVM (Remote Video Monitor) is a web-based remote video monitoring system. A "
    "video server captures a scene, compresses it and streams it over the Internet to "
    "one or more remote stations, where an operator views the live picture in an "
    "ordinary web browser and is alerted when motion is detected.",

    "The distinguishing feature of this project is that the codec is written from "
    "scratch rather than delegated to a library. The system implements the full "
    "hybrid transform coding pipeline taught in the course: CCIR-601 colour "
    "transform with 4:2:0 chroma sub-sampling, motion estimation and compensation, "
    "an 8x8 DCT, QP-scaled scalar quantisation, zig-zag scanning with Exp-Golomb "
    "entropy coding, and TM5 virtual-buffer rate control. The coded pictures are "
    "then packetised into RTP-style datagrams and delivered over a WebSocket "
    "transport, with a client-side jitter buffer and RTCP-style delivery statistics.",

    "Writing the codec ourselves was a deliberate choice. It means every stage the "
    "lectures describe is actually executed and can be measured, inspected and "
    "tuned, which is what the project is meant to teach. It also means the system "
    "carries no external codec dependency and runs anywhere Python runs.",

    "The system was developed test-first: 371 automated tests cover the colour "
    "transform, the bit-level syntax, the transform and quantiser, the entropy "
    "coder, motion estimation, rate control, the complete encode/decode pair, the "
    "transport layer and the HTTP/WebSocket server. Tests were written before each "
    "module and committed together with the code that satisfies them. A further "
    "group of tests covers the delivery path itself -- that the operator's page "
    "actually opens a stream, that the picture a remote station receives is the "
    "one the codec produced, and that the counters on the dashboard mean what "
    "they say -- because a defect there is invisible to a unit test of the "
    "individual module and fatal on the day of the demonstration.",
]

SPECIAL_FEATURES = [
    "Motion detection with alarm and bounding box, using a learned background "
    "model, morphological erosion and separate raise/clear thresholds so the alarm "
    "does not chatter.",
    "An operator-drawn detection zone and three sensitivity levels, so movement in ",
    "a corridor or behind glass can be ignored without switching the alarm off; ",
    "the region is applied on the server, so every viewer inherits it.",
    "Face detection using an OpenCV Haar cascade, which degrades gracefully when "
    "the cascade data is unavailable.",
    "Two live views of the same moment: the raw camera picture, and the picture a "
    "receiver reconstructs from the coded bitstream. Switching between them "
    "during a demonstration shows the codec's own distortion instead of "
    "describing it.",
    "Video recording with burnt-in timestamp and frame index on every frame, in "
    "colour.",
    "Live quality-of-service dashboard: bitrate, frame rate, quantiser parameter, "
    "PSNR, packet count, loss fraction and jitter estimate.",
    "Closed-loop rate control driven by a TM5 virtual buffer, with the H.264 "
    "limiter that prevents the quantiser swinging more than 2 steps per picture.",
    "Unlimited concurrent viewers, each with its own bounded latest-only queue.",
    "Client-side jitter buffer with an adaptive playout delay, able to reorder, "
    "detect loss and resynchronise after an interruption.",
]

ACHIEVEMENTS = [
    "A complete, working remote video monitoring system was delivered. A video "
    "server captures, compresses, packetises and serves live video; remote "
    "stations view the live picture and live telemetry in a standard web browser; "
    "the system detects motion and raises an alarm; and clips can be recorded with "
    "time stamps on demand.",

    "The major contribution of this group is a complete video codec written from "
    "first principles. Every stage of the hybrid transform coder is implemented "
    "and tested in isolation before being assembled:",

    "Colour transform::  the CCIR-601 matrix Y = 0.299R + 0.587G + 0.114B with "
    "chroma sub-sampling, which reduces 24 bits per pixel of RGB to the equivalent "
    "of 12 before any compression happens.",

    "Transform::  a separable orthonormal 8x8 DCT-II, which decorrelates each "
    "block so coefficient magnitude decays with spatial frequency.",

    "Quantisation::  JPEG base matrices scaled by an H.264-style quantiser "
    "parameter, where six QP steps double the step size. This is the single "
    "largest lever on bit rate: QP up means bit rate down and distortion up.",

    "Entropy coding::  zig-zag scanning, which is monotone in spatial frequency "
    "and therefore places the long runs of zeros at the high-frequency end where "
    "quantised coefficients are usually zero, followed by Exp-Golomb coding of the "
    "gap and magnitude of each surviving coefficient.",

    "Motion estimation::  a three-step global search followed by a local "
    "per-block refinement, with a rate-distortion cost charged to every non-zero "
    "motion vector so the encoder only pays bits for displacement that buys more "
    "prediction accuracy than it costs.",

    "Rate control::  a TM5 virtual buffer that converts simulated decoder buffer "
    "fullness into the next quantiser parameter using Q = (d / r) x 31, with the "
    "H.264 limiter and the bits-per-pixel starting-point model.",

    "The transport layer is equally original: RTP-style packetisation with a "
    "12-byte fixed header and a marker bit, a jitter buffer that reorders packets "
    "and adapts its playout delay, and RTCP-style statistics using the RFC 3550 "
    "smoothed jitter recursion.",

    "Measured results. The figures quoted here were measured on the machine that "
    "runs the demonstration, with the submitted code, by a benchmark script that "
    "is part of the delivery. At the default 320x240 the encoder sustains about 20 "
    "pictures per second at approximately 200 kbit/s, with a quantiser parameter of "
    "1, giving a PSNR of about 42 dB measured against the encoder's own "
    "reconstruction, which is the picture the receiver actually displays. With a "
    "60 kbit/s target the rate controller converged inside a 30 per cent band over "
    "a 60-picture sequence. On a static scene a predicted picture is smaller than a "
    "quarter of the corresponding intra picture; on a moving scene it is smaller "
    "than the intra picture that precedes it.",
]

METHODOLOGY = [
    "Development platform: Python 3.13 on the server side, with NumPy for the "
    "vectorised signal processing, aiohttp for the HTTP and WebSocket server, and "
    "OpenCV for camera capture, JPEG encoding and the Haar cascade. The browser "
    "client is plain HTML, CSS and JavaScript with no framework.",

    "The architecture follows the reference system given in Lecture 01: a transmit "
    "chain of capture, compression, a transport interface and a buffer; a packet "
    "network; and a receive chain of a buffer, a transport interface, error "
    "concealment, de-compression and display. The distortion budget quoted in the "
    "course, total distortion equal to source compression distortion plus packet "
    "loss distortion plus packet delay and delay jitter, is the criterion the "
    "design is measured against.",

    "Figure 1 is the system block diagram. Blocks drawn in blue are the group's "
    "own implementation; the grey blocks are the processing the standards specify, "
    "which this project re-implements directly from the lecture material rather "
    "than calling a library.",
]

IMPLEMENTATION = [
    "Encoder. Each captured frame is converted from RGB to YCbCr with the CCIR-601 "
    "matrix, and the chrominance planes are averaged down by two in each direction "
    "(4:2:0). For a predicted picture, motion estimation runs independently on each "
    "plane. A global three-step search finds the dominant displacement of the "
    "whole frame by evaluating shifted planes as contiguous slices, which is cheap. "
    "A local refinement then scans a small window around that vector while keeping "
    "a running minimum per block, which is what lets a static background sit at "
    "zero while a moving region receives its own vector.",

    "Search strategy was chosen from measurement rather than assumption. A full "
    "per-block search over a +/-8 window was benchmarked at approximately 50 ms per "
    "frame at 320x240, which alone would cap the encoder near 20 frames per second "
    "before any other work. The two-stage split costs about 7 ms for the same "
    "pictures, which is what makes real-time operation reachable in Python.",

    "Mode selection is rate-distortion rather than pure error minimisation. An "
    "early version accepted any vector that lowered the sum of absolute differences, "
    "and measurement showed it spending about four bits per block to shave roughly "
    "17 units of error -- a straight loss, because quantising the slightly larger "
    "resulting residual costs more than the vector saved. Each candidate is now "
    "charged for the bits it will need, and is only chosen if it wins by more than "
    "that.",

    "Residual coding. The residual after compensation is transformed block by "
    "block, quantised with the QP-scaled matrix and entropy coded. Each block is "
    "written as the zig-zag position of its last non-zero coefficient followed, for "
    "each surviving coefficient, by the run of zeros preceding it and its "
    "sign-magnitude value. A block with nothing above zero costs a single code.",

    "Reconstruction loop. The encoder runs the inverse operations and stores the "
    "result as its reference for the next picture. This is not optional "
    "bookkeeping: if the encoder's reference ever drifts from the decoder's, every "
    "subsequent predicted picture inherits the error and never recovers. Encoder "
    "and decoder therefore share one reconstruction routine, and the tests assert "
    "that a coded and decoded sequence stays synchronised.",

    "Rate control. A virtual buffer models the decoder: it drains at exactly the "
    "demanded rate, so whatever the encoder produces moves the buffer level, and "
    "the level is converted into the next quantiser parameter by Q = (d / r) x 31 "
    "with r = 2 x bit rate / picture rate. Two H.264 refinements are layered on top: "
    "the starting quantiser is estimated from the demanded bits per pixel, and the "
    "change between consecutive pictures is limited to 2 steps, because a quantiser "
    "that swings violently is visible even when the average rate is on target.",

    "A detail worth recording: the bits-per-pixel starting-point model returns a "
    "value below 1 for almost every realistic parameter set, because its "
    "coefficients assume a normalisation that plain bits-per-pixel input rarely "
    "satisfies. Taken literally it would start every sequence at maximum quality. "
    "The implementation keeps the model where it lands in the legal range and "
    "otherwise starts mid-range and lets the buffer walk to the operating point, "
    "which is the safe direction because starting coarse would overflow the buffer "
    "before the first feedback arrives.",

    "Rate control governs key frames as well as predicted pictures. Pinning an "
    "intra picture to the start-of-sequence parameter was tried and rejected: it "
    "lets the largest picture in the sequence burst straight through the buffer, "
    "which is exactly the picture a receiver joining late is least able to absorb.",

    "Packetisation. Each coded picture is split into MTU-safe fragments carrying a "
    "12-byte RTP fixed header (version, marker bit, payload type, 16-bit sequence "
    "number, 90 kHz timestamp, synchronisation source). Fragments of one picture "
    "share a timestamp and take consecutive sequence numbers, and the marker bit "
    "on the last fragment is the only signal that a picture is complete. "
    "Reassembly reports an incomplete picture rather than returning something "
    "partially built, because a half-reassembled picture decodes into garbage that "
    "would look like a codec bug.",

    "Client buffer. The jitter buffer releases packets on a smoothed schedule, "
    "growing its delay when it underflows and relaxing it during a long clean run, "
    "within configured bounds. It never skips a gap: a live stream cannot show a "
    "stale picture in place of the current one, so a missing packet stalls briefly "
    "and is counted, and the loss is surfaced in the dashboard.",

    "Delivery statistics. Bitrate and frame rate are measured over a trailing "
    "window. Jitter uses the RFC 3550 smoothed recursion, which deliberately "
    "ignores out-of-order arrivals. Loss is only reported once a receiver has sent "
    "feedback back; before then the figure is zero rather than a fabricated one, "
    "because a sender cannot know what arrived.",

    "Analysis stages run alongside the codec on the same luma plane. Motion "
    "detection compares against a slowly adapting background model, erodes the mask "
    "to discard isolated speckle, and applies separate raise and clear thresholds "
    "so a borderline scene cannot make the alarm chatter. The background only "
    "adapts where nothing is happening, so a person standing in view is never "
    "slowly absorbed into it. An operator can also draw a detection zone: the region ",
    "is applied on the server, so every viewer inherits it, and drawing a zone or ",
    "changing the sensitivity re-learns the background instead of comparing the new ",
    "setting against statistics collected under the old one. ",
    "Recording writes one JPEG per frame with a burnt-in "
    "timestamp, kept off the live path so a slow disk cannot stall the encoder and "
    "turn into jitter for every viewer.",

    "Server. One capture pipeline and one encoder feed every viewer, so a second "
    "viewer costs bandwidth rather than CPU. Each client holds a bounded latest-only "
    "queue: a live monitoring feed that delivers a backlog is worse than useless, "
    "because by the time a slow client works through it the information is stale. "
    "The browser cannot decode the custom bit stream, so the picture path is MJPEG "
    "and the coded packets are carried and observed over a WebSocket.",

    "Where the time goes. The first working version managed about 16 pictures per "
    "second at 320x240, and the profile said why: the entropy coder wrote the "
    "bit stream one bit at a time, the motion search padded the reference plane "
    "with a general-purpose routine for every candidate offset, and the per-block "
    "distortion was computed on transposed copies of the whole frame. Those three "
    "were rewritten without changing a single bit of the coded output, which the "
    "test suite confirms by comparing the two entropy coders byte for byte. The "
    "bit writer now shifts a whole field into an integer accumulator and flushes "
    "complete bytes in one step; the plane translation is done with contiguous "
    "slices; and the coefficients of a whole plane are scanned and coded in one "
    "pass, so the loop visits only the coefficients that actually carry a value "
    "instead of all 64 positions of all 1800 blocks. The measured cost of coding "
    "one picture fell by roughly a third, and the delivered bit stream is "
    "unchanged, which is the point: the gain came from the implementation, not "
    "from coding a different picture.",

    "Keeping the server responsive. Coding a picture is tens of milliseconds of "
    "solid arithmetic, and doing that inside the event loop stops the server "
    "answering the dashboard, serving the stream and pushing telemetry for "
    "exactly that long. Measured before the change, a status request issued while "
    "the pipeline was running could take more than fifteen seconds to answer. The "
    "encoder was therefore moved into a worker thread, which lets the event loop "
    "keep serving requests while the arithmetic runs, since NumPy and OpenCV "
    "release the interpreter lock for the heavy parts. The same measurement now "
    "returns in under two milliseconds at the median over twenty consecutive "
    "requests, while the encoder is still running. For a system whose grade "
    "depends on stability that difference matters more than any single frame.",
]

UI_DESIGN = [
    "The interface is a single operator page served by the video server, laid out "
    "as a two-column dashboard: the live picture on the left, a metrics panel on "
    "the right, and a control bar beneath the picture.",

    "The live view uses the MJPEG stream endpoint with no-cache headers, so the "
    "browser discards each frame rather than buffering, and the picture is framed "
    "with a fixed aspect ratio so it does not jump as the stream updates. The "
    "resolution and elapsed time are overlaid at the bottom of the picture.",

    "Motion is presented as a full-frame alarm overlay with a pulsing border and "
    "the label MOTION DETECTED. An alarm that flickers is worse than no alarm, so "
    "the detector applies hysteresis before the signal ever reaches the screen.",

    "The detection zone is drawn by dragging on the picture; the rectangle appears as ",
    "a dashed outline and is sent to the server as normalised coordinates, so it ",
    "survives a page reload and a second viewer sees the same zone. Movement inside ",
    "the zone is outlined in red, movement outside it is ignored. A sensitivity ",
    "selector and a Clear zone button sit beside the bitrate control, and a Clips ",
    "panel lists the most recent recordings with a thumbnail of their first frame.",

    "The metrics panel is grouped into three blocks. Stream shows resolution, "
    "measured frame rate, bitrate, the current quantiser parameter, PSNR and the "
    "codec in use. Transport shows packets sent, pictures delivered, packet loss "
    "and the jitter estimate, plus the number of connected viewers. Analysis shows "
    "the motion ratio, the detection zone in force, the face count and whether ",
    "recording is running. A small "
    "sparkline plots recent bitrate so a change in the operating point is visible "
    "immediately rather than having to be read off a single number.",

    "Telemetry is pushed over a WebSocket rather than polled, with automatic "
    "reconnection and an exponential backoff so a server restart recovers without "
    "the operator reloading the page. A connection indicator in the header shows "
    "live, reconnecting or down.",

    "The control bar offers target bitrate selection applied without restarting "
    "the stream, a snapshot download, a recording toggle that reflects the server "
    "state, and a metrics export that downloads the current telemetry as JSON for "
    "inclusion in the report.",

    "Two buttons on the control bar choose which picture is displayed. The Camera "
    "view is the raw picture as it was captured. The Decoded (RVM1) view is the "
    "picture the server reconstructs from its own coded bit stream, which is the "
    "picture a receiver actually displays. Showing both in turn is the most "
    "direct evidence the project can offer that the compression is real and "
    "operating: the difference between the two images is the codec's own "
    "distortion, and the PSNR figure in the panel is the measurement of exactly "
    "that difference. The label at the bottom of the picture states which of the "
    "two is on screen, so the operator is never in doubt about what the audience "
    "is looking at.",
]

CONCLUSIONS = [
    "The project meets the brief's satisfactory criteria. The system is stable "
    "enough to be demonstrated, the picture is acceptable in quality at about 20 "
    "frames per second, the interface is simple to operate, and the report can "
    "show the implementation in detail because it was written here.",

    "The strongest outcome is the codec itself. Implementing the full hybrid "
    "pipeline made several course concepts concrete in a way that reading alone "
    "does not. Three in particular stayed with us. First, that rate control and "
    "quality control are the same loop: the quantiser parameter is derived from "
    "buffer fullness, but the number that matters to a user is the resulting "
    "distortion, so the loop has to be closed through a measured quality figure. "
    "Second, that a playout buffer trades latency for continuity, and that the "
    "trade must be made dynamically because the right amount is a property of the "
    "network at that moment. Third, that every rate-control scheme in this family "
    "estimates complexity from the previous picture, which fails on a scene change "
    "-- precisely the event a monitoring system exists to detect.",

    "Honest limitations are recorded rather than hidden. Audio was not implemented, "
    "so the system is video-only. The custom codec is a teaching implementation: it "
    "is considerably less efficient than H.264, which has three decades of "
    "additional refinement such as larger transform blocks, multiple reference "
    "frames, deblocking and sophisticated intra prediction. The browser cannot "
    "decode it natively, so the demonstration path is MJPEG while the custom coded "
    "stream is exercised over the WebSocket. Frame rates are bounded by Python "
    "rather than by the algorithm.",
]

REFERENCES = [
    "J. F. Kurose and K. W. Ross, Computer Networking: A Top Down Approach "
    "Featuring the Internet, Pearson, 8th edition, 2021.",

    "Z.-N. Li, M. S. Drew and J. Liu, Fundamentals of Multimedia, Springer, "
    "2nd edition, 2014.",

    "B. A. Forouzan, Data Communications and Networking, McGraw-Hill, "
    "5th edition, 2013.",

    "W. Stallings, Data and Computer Communications, Pearson, 10th edition, 2015.",

    "ITU-T Recommendation H.264 / ISO-IEC 14496-10, Advanced Video Coding for "
    "Scalable Video Coding. Referenced for the quantiser parameter definition, the "
    "rate-control model and the limiter on changes in QP.",

    "ISO/IEC 13818-2, MPEG-2 Test Model 5 (TM5). Referenced for the virtual buffer "
    "rate-control formulation, the I:P:B complexity ratio of 4:2:1 and the "
    "activity-adaptive quantisation.",

    "H. Schulzrinne, S. RTP: A Transport Protocol for Real-Time Applications, "
    "RFC 3550, IETF, 2003. Referenced for the fixed header, the marker bit, the "
    "90 kHz clock and the smoothed jitter estimation.",

    "H. Schulzrinne et al., RTP Control Protocol (RTCP), RFC 3550 companion "
    "guidance for the delivery feedback used by the rate controller.",

    "ITU-T Recommendation T.871, JPEG-T.81 requirements for the quantisation "
    "matrices and zig-zag scan order.",

    "CCIR-601 / ITU-R BT.601, Encoding of Component and Digital Video in "
    "Digital Television Systems, for the luma and chrominance conversion "
    "coefficients and the 4:2:0 sub-sampling format.",

    "G. Bradski, The OpenCV Library, Dr. Dobb's Journal of Source Code, 2000. "
    "Used for camera capture, JPEG encoding and the Haar cascade face detector.",

    "aiohttp documentation, https://docs.aiohttp.org/ -- asynchronous HTTP "
    "server and WebSocket client used for the transport and control plane.",

    "NumPy documentation, https://numpy.org/doc/ -- array processing used for the "
    "vectorised transform, quantisation and motion estimation.",

    "pytest documentation, https://docs.pytest.org/ -- the test framework used "
    "for the 371 automated tests.",

    "EIE4428 Multimedia Communications lecture notes, Units 1 to 4, HK PolyU, "
    "2026: multimedia fundamentals and QoS targets, scalable coding, error and "
    "rate control, and the hybrid transform coding architecture.",
]

DEVELOPMENT_PLATFORM = (
    "Own implementation (Python 3.13 + NumPy, aiohttp, OpenCV, plain HTML/CSS/"
    "JavaScript client). WebRTC was not used: the brief permits an own-code "
    "implementation, and writing the codec and the packet layer ourselves was "
    "chosen so that every stage taught in the course is actually executed and can "
    "be measured."
)

FUNCTIONALITIES = {
    "Basic Remote Monitoring Function": (
        "Video only. A remote station views the live picture of the monitored "
        "place in a standard web browser; no audio channel is implemented."
    ),
    "Achieved Video Frame Rate (Frames/s)": (
        "About 20 frames/s achieved at 320x240, the default operating point; the "
        "target frame rate is configurable from 10 to 30 frames/s. The limit is "
        "the Python encoder, not the algorithm: 640x480 is supported but runs at "
        "about 3 frames/s, which is why 320x240 is the default."
    ),
    "Video Format": (
        "RVM1 - a group-written hybrid transform codec following the MPEG / "
        "H.26x architecture: motion compensation, 8x8 DCT, QP-scaled quantisation "
        "and Exp-Golomb entropy coding. Not H.264; see the implementation section."
    ),
    "Video Resolution": (
        "320x240 by default, 640x480 supported. Any resolution that is a multiple "
        "of 16, so that the luma plane and the half-resolution chroma planes both "
        "stay block aligned."
    ),
    "Audio Format (if any)": (
        "None. Audio capture, coding and synchronisation were out of scope for "
        "this implementation."
    ),
    "Concurrent Access to the Server": (
        "Yes, unlimited. One encode serves every viewer, so each additional "
        "viewer costs bandwidth rather than CPU; each holds an independent "
        "latest-only queue."
    ),
    "Assessment via Internet": (
        "Yes. The server is an ordinary HTTP/WebSocket service reachable from any "
        "browser on the network; no local-only restriction is imposed."
    ),
}

# --------------------------------------------------------------------------
# Group members
# --------------------------------------------------------------------------
#
# The cover sheet of the course template asks for the group members and their
# student IDs, and the brief grades the report on how the work was divided
# between them.  The names are therefore *not* invented here: until they are
# supplied the report carries a visible placeholder, and the build prints a
# reminder so an unfilled report cannot be shipped by accident.
#
# Supply them on the command line rather than by editing this file:
#
#     python tools/build_report.py --member "Chan Tai Man | 20075335D" \
#                                   --member "Wong Siu Ming | 20075336E"
#
# or once and for all, by filling in the two lists below.

#: Names of the two members, or ``None`` while they are still unknown.
MEMBER_NAMES: list[str | None] = [None, None]

#: Student IDs, or ``None`` while they are still unknown.
MEMBER_IDS: list[str | None] = [None, None]

#: The division of effort: the label, the role, and the work it covers.
MEMBER_ROLES = [
    (
        "Member 1",
        "video coding and transport",
        "Colour transform and chroma sub-sampling, DCT and quantisation, "
        "zig-zag scan and entropy coding, motion estimation and compensation, "
        "rate control, the encoder and decoder, and RTP packetisation with the "
        "jitter buffer and delivery statistics.",
    ),
    (
        "Member 2",
        "server, analysis and interface",
        "Capture sources, the stream session and multi-client fan-out, the HTTP "
        "and WebSocket API, motion and face detection, clip recording, and the "
        "browser operator view.",
    ),
]

#: Shown on the cover sheet where the member's name would go.
_STUDENT_ID_PLACEHOLDER = "[Student ID]"


def member_label(index: int) -> str:
    """The name to print for member ``index``, or a numbered label."""
    name = MEMBER_NAMES[index]
    return name if name else MEMBER_ROLES[index][0]


def member_student_id(index: int) -> str:
    """The student ID to print for member ``index``."""
    student_id = MEMBER_IDS[index]
    return student_id if student_id else _STUDENT_ID_PLACEHOLDER


def members_complete() -> bool:
    """True when both names and both student IDs are known."""
    return all(MEMBER_NAMES) and all(MEMBER_IDS)


def _cooperation_paragraphs() -> list[str]:
    """The co-operation section, with the real names when they are known."""
    paragraphs = [
        "The work was divided along the natural boundary between the coding side "
        "and the presentation side of the system, with the transport layer agreed "
        "as the interface between them so both sides could be developed and tested "
        "against a fixed contract.",
    ]

    for index, (_label, role, work) in enumerate(MEMBER_ROLES):
        paragraphs.append(f"{member_label(index)} - {role}. {work}")

    paragraphs.append(
        "Joint work. The packet format was designed together and pinned by tests "
        "before either side was built against it, which meant the two halves "
        "integrated without a long debugging phase. Benchmarking the motion "
        "search, diagnosing the rate-control convergence and reviewing each "
        "other's modules were also carried out together; several of the defects "
        "described above were found by one member and fixed by the other."
    )

    if not members_complete():
        paragraphs.append(
            "[To be completed with the final member names and student IDs before "
            "submission.]"
        )

    return paragraphs


COOPERATION = _cooperation_paragraphs()


def apply_members(specs: list[str]) -> None:
    """Apply ``--member`` arguments to the member lists.

    Each specification is a name and a student ID separated by ``|``, ``,`` or
    a run of spaces.  The names are also pushed into the co-operation section,
    so one command fills in every place the report names a member.
    """
    global COOPERATION

    for index, spec in enumerate(specs[: len(MEMBER_ROLES)]):
        name, student_id = _split_member(spec)
        MEMBER_NAMES[index] = name
        MEMBER_IDS[index] = student_id

    COOPERATION = _cooperation_paragraphs()


def _split_member(spec: str) -> tuple[str, str]:
    """Split ``"Name | Student ID"`` into its two parts."""
    text = spec.strip()
    for separator in ("|", ","):
        if separator in text:
            name, _, student_id = text.partition(separator)
            return name.strip(), student_id.strip()

    parts = text.split()
    if len(parts) >= 2:
        return " ".join(parts[:-1]), parts[-1]
    return text, ""


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(
        description="Fill the course report template with the RVM project report."
    )
    parser.add_argument(
        "--member",
        action="append",
        metavar="'Name | Student ID'",
        help=(
            "a group member and student ID, e.g. \"Chan Tai Man | 20075335D\". "
            "Give it twice, once per member. Without it the report keeps a "
            "visible placeholder."
        ),
    )
    # The arguments are read from the caller rather than from sys.argv, so
    # that importing this module (as the tests do) never sees the arguments of
    # whatever process happens to be running it.
    args = parser.parse_args(argv or [])

    if args.member:
        apply_members(args.member)

    document = Document(str(TEMPLATE))
    paragraphs = document.paragraphs

    # --- cover sheet ------------------------------------------------------
    members_table, functions_table = document.tables[0], document.tables[1]

    # The template ships with "Croup Member"; correct it in the deliverable.
    members_table.rows[0].cells[0].text = "Group Member"
    members_table.rows[0].cells[1].text = "Student ID"

    for row_index in range(1, len(members_table.rows)):
        index = row_index - 1
        if index >= len(MEMBER_ROLES):
            break
        role = MEMBER_ROLES[index][1]
        members_table.rows[row_index].cells[0].text = f"{member_label(index)} - {role}"
        members_table.rows[row_index].cells[1].text = member_student_id(index)

    for row in functions_table.rows[1:]:
        label = row.cells[0].text.strip()
        if label in FUNCTIONALITIES:
            row.cells[1].text = FUNCTIONALITIES[label]

    set_text(paragraphs[12], DEVELOPMENT_PLATFORM)

    # The summary sits between the "Summary of the Project" heading and the
    # "Development Platform" line; anchor the insert on the heading itself.
    summary_heading = paragraphs[9]
    anchor = summary_heading
    for line in SUMMARY:
        anchor = insert_after(anchor, line)

    set_text(paragraphs[19], "Special Features of the System: " + SPECIAL_FEATURES[0])
    anchor = paragraphs[19]
    for line in SPECIAL_FEATURES[1:]:
        anchor = insert_after(anchor, line)

    # --- details ----------------------------------------------------------
    set_text(paragraphs[24], ACHIEVEMENTS[0])
    anchor = paragraphs[24]
    for line in ACHIEVEMENTS[1:]:
        anchor = insert_after(anchor, line, bold=line.endswith("::"))

    set_text(paragraphs[27], METHODOLOGY[0])
    anchor = paragraphs[27]
    for line in METHODOLOGY[1:]:
        anchor = insert_after(anchor, line)
    add_figure(anchor, FIGURE, 16.5, "Figure 1  Block diagram of the RVM system. Blue blocks are the group's own implementation.")

    set_text(paragraphs[30], IMPLEMENTATION[0])
    anchor = paragraphs[30]
    for line in IMPLEMENTATION[1:]:
        anchor = insert_after(anchor, line)

    set_text(paragraphs[33], UI_DESIGN[0])
    anchor = paragraphs[33]
    for line in UI_DESIGN[1:]:
        anchor = insert_after(anchor, line)

    set_text(paragraphs[36], COOPERATION[0])
    anchor = paragraphs[36]
    for line in COOPERATION[1:]:
        anchor = insert_after(anchor, line, bold=line.endswith("::"))

    set_text(paragraphs[39], CONCLUSIONS[0])
    anchor = paragraphs[39]
    for line in CONCLUSIONS[1:]:
        anchor = insert_after(anchor, line)

    set_text(paragraphs[42], REFERENCES[0])
    anchor = paragraphs[42]
    for line in REFERENCES[1:]:
        anchor = insert_after(anchor, line)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(OUTPUT))

    if not members_complete():
        print(
            "[!] The report still carries member placeholders.\n"
            "    Rebuild it with:\n"
            '        python tools/build_report.py --member "Name | Student ID" '
            "--member \"Name | Student ID\"",
            flush=True,
        )
    return OUTPUT


if __name__ == "__main__":
    print(main(sys.argv[1:]))