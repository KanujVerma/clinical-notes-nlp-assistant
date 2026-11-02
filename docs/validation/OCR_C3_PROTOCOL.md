# OCR campaign 3 protocol

Study `ocr-c3-apple-vision-v1` compares one frozen Apple Vision configuration with the existing GLM-OCR `B8192` control. It does not continue campaign 1 or campaign 2, and it does not retune those results.

The only candidate is `V1_apple_vision_accurate_raw`: `VNRecognizeTextRequest`, recognition level `accurate`, language correction off, language `en-US`, automatic language detection off, no custom words, minimum text height 0, and the whole prepared page. The top candidate is scored. Up to three candidates are retained. Revision `3` is the accurate revision reported by the installed Vision framework on macOS 27.0.1 build `26A434`. English is in the supported language list. Vision does not expose an OCR weight hash, so the OS build and revision are the runtime identity.

Images are prepared only by `evaluation.public_amr_benchmark.infer_image`. The Swift helper decodes that JPEG and does not resize, sharpen, deskew, or apply a second EXIF rotation. A prepared JPEG with an orientation tag other than 1 is rejected.

Reading order `vision_reading_order_v1` sorts observations by top y, then left x, then the original index. Invalid geometry sorts last and its text is kept. A wide horizontal gap between vertically overlapping boxes sets `reading_order_uncertain` and does not drop the page. Joined observations are one newline. The scoring unit remains the source page.

The screen is the existing eight development AMR documents and 64 development Rx crops. Confirmation, only after every screen gate passes, is the 20 development AMR documents and 256 development Rx crops. The AMR holdout, the Rx official-test holdout, and the Rx internal-validation split stay sealed.

The primary gate is a 10 percent relative reduction in paired normalized AMR CER against a verified `B8192` baseline. Strict AMR CER and WER, normalized AMR WER, paired Rx CER and WER, coverage, and critical-token hits must not worsen. Critical false positives must not increase. A whitespace-only change is not an accuracy win. Undefined CER stays undefined. The product p95 target is 60 seconds for a cold helper process. Eight pages make that p95 the slowest page. The compute ceiling is 7,200 seconds, with a 120-second page deadline.

`OCR_C3_ENABLED` defaults off. This study does not replace GLM-OCR and does not open a holdout.
