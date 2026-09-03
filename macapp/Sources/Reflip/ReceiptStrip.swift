import SwiftUI

/// The strip at the bottom: what the rewrite actually did.
///
/// This is the part of the window that the forty other watermark removers do not have.
/// Rewriting text is ordinary; the share of the detector's windows that carry an edit,
/// and what it cost to get there, is the answer a person came for. Every figure is read
/// from the receipt reflip printed and none is recomputed from the text on screen.
struct ReceiptStrip: View {
    let receipt: Receipt?

    /// The share of five-token windows reflip's own coverage loop re-asks below. The
    /// number is reflip's, from the benchmark in the README, and the colour is the only
    /// thing this window adds to it.
    private static let enough = 0.9

    var body: some View {
        Group {
            if let receipt {
                figures(receipt)
            } else {
                Text("Nothing has been rewritten yet. After a rewrite this strip says how "
                     + "much of the text changed, how much of what a detector looks at was "
                     + "touched, and what it cost in tokens and seconds.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.thinMaterial)
        .overlay(alignment: .top) { Divider() }
    }

    private func figures(_ receipt: Receipt) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 22) {
            figure(Format.percent(receipt.editRatio), "of the words changed")
                .help("The share of words in the result that are not the same word "
                      + "found in the same place in the original text.")

            if let coverage = receipt.coverage {
                figure(Format.percent(coverage), "of the detector windows carry an edit",
                       tint: coverage >= Self.enough ? .green : .orange)
                    .help("The share of five-token windows a watermark detector checks "
                          + "that contain at least one edited word. At or above "
                          + "\(Format.percent(Self.enough)) every position the detector "
                          + "scores has been touched.")
            } else {
                // The caption stays short so a long sentence cannot stretch this row;
                // reflip's own reason for why, when it has one, lives in the tooltip
                // instead of this window inventing one generic reason for every cause:
                // no tokenizer named, `transformers` not installed, or `--no-coverage`.
                figure("not measured", "coverage was not checked", tint: .secondary)
                    .help(receipt.coverageNote ?? "Coverage was not checked for this "
                          + "rewrite.")
            }

            figure(Format.count(receipt.tokens), "tokens spent")
                .help("Prompt and completion tokens billed by the model across every "
                      + "call this rewrite made.")
            figure(Format.seconds(receipt.seconds), "seconds")
                .help("Wall-clock time this rewrite took, start to finish.")

            Spacer(minLength: 12)

            VStack(alignment: .trailing, spacing: 2) {
                Text("\(Format.count(receipt.edits)) of \(Format.count(receipt.words)) words")
                    .monospacedDigit()
                Text(trailing(receipt))
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
    }

    private func figure(_ value: String, _ caption: String,
                        tint: Color = .primary) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(value)
                .font(.system(.title3, design: .rounded).weight(.semibold))
                .foregroundStyle(tint)
                .monospacedDigit()
            Text(caption)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }

    /// Which model did it, and how many times it was asked. A transform that never
    /// opens a socket says so instead, because "0 calls to" reads as a failure.
    private func trailing(_ receipt: Receipt) -> String {
        guard let model = receipt.model, !model.isEmpty, receipt.llmCalls > 0 else {
            return "\(receipt.transform), with no model"
        }
        let calls = receipt.llmCalls == 1 ? "one call" : "\(receipt.llmCalls) calls"
        return "\(calls) to \(model)"
    }
}
