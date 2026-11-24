"""Unicode 17.0 字元屬性，用於聊天室過濾。"""

# Unicode 17.0 Script=Latin, Emoji_Presentation, and text-default Emoji ranges.
# https://www.unicode.org/Public/17.0.0/ucd/Scripts.txt
# https://www.unicode.org/Public/17.0.0/ucd/emoji/emoji-data.txt
# Unicode data terms: https://www.unicode.org/license.txt
LATIN_RANGES = (
    r"\u0041-\u005a\u0061-\u007a\u00aa\u00ba\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u02b8\u02e0-\u02e4"
    r"\u1d00-\u1d25\u1d2c-\u1d5c\u1d62-\u1d65\u1d6b-\u1d77\u1d79-\u1dbe\u1e00-\u1eff\u2071\u207f"
    r"\u2090-\u209c\u212a-\u212b\u2132\u214e\u2160-\u2188\u2c60-\u2c7f\ua722-\ua787\ua78b-\ua7dc"
    r"\ua7f1-\ua7ff\uab30-\uab5a\uab5c-\uab64\uab66-\uab69\ufb00-\ufb06\uff21-\uff3a\uff41-\uff5a"
    r"\U00010780-\U00010785\U00010787-\U000107b0\U000107b2-\U000107ba\U0001df00-\U0001df1e"
    r"\U0001df25-\U0001df2a"
)
EMOJI_PRESENTATION_RANGES = (
    r"\u231a-\u231b\u23e9-\u23ec\u23f0\u23f3\u25fd-\u25fe\u2614-\u2615\u2648-\u2653\u267f\u2693\u26a1"
    r"\u26aa-\u26ab\u26bd-\u26be\u26c4-\u26c5\u26ce\u26d4\u26ea\u26f2-\u26f3\u26f5\u26fa\u26fd\u2705"
    r"\u270a-\u270b\u2728\u274c\u274e\u2753-\u2755\u2757\u2795-\u2797\u27b0\u27bf\u2b1b-\u2b1c\u2b50\u2b55"
    r"\U0001f004\U0001f0cf\U0001f18e\U0001f191-\U0001f19a\U0001f1e6-\U0001f1ff\U0001f201\U0001f21a\U0001f22f"
    r"\U0001f232-\U0001f236\U0001f238-\U0001f23a\U0001f250-\U0001f251\U0001f300-\U0001f320"
    r"\U0001f32d-\U0001f335\U0001f337-\U0001f37c\U0001f37e-\U0001f393\U0001f3a0-\U0001f3ca"
    r"\U0001f3cf-\U0001f3d3\U0001f3e0-\U0001f3f0\U0001f3f4\U0001f3f8-\U0001f43e\U0001f440"
    r"\U0001f442-\U0001f4fc\U0001f4ff-\U0001f53d\U0001f54b-\U0001f54e\U0001f550-\U0001f567\U0001f57a"
    r"\U0001f595-\U0001f596\U0001f5a4\U0001f5fb-\U0001f64f\U0001f680-\U0001f6c5\U0001f6cc"
    r"\U0001f6d0-\U0001f6d2\U0001f6d5-\U0001f6d8\U0001f6dc-\U0001f6df\U0001f6eb-\U0001f6ec"
    r"\U0001f6f4-\U0001f6fc\U0001f7e0-\U0001f7eb\U0001f7f0\U0001f90c-\U0001f93a\U0001f93c-\U0001f945"
    r"\U0001f947-\U0001f9ff\U0001fa70-\U0001fa7c\U0001fa80-\U0001fa8a\U0001fa8e-\U0001fac6\U0001fac8"
    r"\U0001facd-\U0001fadc\U0001fadf-\U0001faea\U0001faef-\U0001faf8"
)
TEXT_EMOJI_RANGES = (
    r"\u0023\u002a\u0030-\u0039\u00a9\u00ae\u203c\u2049\u2122\u2139\u2194-\u2199\u21a9-\u21aa\u2328\u23cf"
    r"\u23ed-\u23ef\u23f1-\u23f2\u23f8-\u23fa\u24c2\u25aa-\u25ab\u25b6\u25c0\u25fb-\u25fc\u2600-\u2604\u260e"
    r"\u2611\u2618\u261d\u2620\u2622-\u2623\u2626\u262a\u262e-\u262f\u2638-\u263a\u2640\u2642\u265f-\u2660"
    r"\u2663\u2665-\u2666\u2668\u267b\u267e\u2692\u2694-\u2697\u2699\u269b-\u269c\u26a0\u26a7\u26b0-\u26b1"
    r"\u26c8\u26cf\u26d1\u26d3\u26e9\u26f0-\u26f1\u26f4\u26f7-\u26f9\u2702\u2708-\u2709\u270c-\u270d\u270f"
    r"\u2712\u2714\u2716\u271d\u2721\u2733-\u2734\u2744\u2747\u2763-\u2764\u27a1\u2934-\u2935\u2b05-\u2b07"
    r"\u3030\u303d\u3297\u3299\U0001f170-\U0001f171\U0001f17e-\U0001f17f\U0001f202\U0001f237\U0001f321"
    r"\U0001f324-\U0001f32c\U0001f336\U0001f37d\U0001f396-\U0001f397\U0001f399-\U0001f39b"
    r"\U0001f39e-\U0001f39f\U0001f3cb-\U0001f3ce\U0001f3d4-\U0001f3df\U0001f3f3\U0001f3f5\U0001f3f7"
    r"\U0001f43f\U0001f441\U0001f4fd\U0001f549-\U0001f54a\U0001f56f-\U0001f570\U0001f573-\U0001f579"
    r"\U0001f587\U0001f58a-\U0001f58d\U0001f590\U0001f5a5\U0001f5a8\U0001f5b1-\U0001f5b2\U0001f5bc"
    r"\U0001f5c2-\U0001f5c4\U0001f5d1-\U0001f5d3\U0001f5dc-\U0001f5de\U0001f5e1\U0001f5e3\U0001f5e8"
    r"\U0001f5ef\U0001f5f3\U0001f5fa\U0001f6cb\U0001f6cd-\U0001f6cf\U0001f6e0-\U0001f6e5\U0001f6e9\U0001f6f0"
    r"\U0001f6f3"
)


# UNICODE LICENSE V3
#
# COPYRIGHT AND PERMISSION NOTICE
#
# Copyright © 1991-2026 Unicode, Inc.
#
# NOTICE TO USER: Carefully read the following legal agreement. BY
# DOWNLOADING, INSTALLING, COPYING OR OTHERWISE USING DATA FILES, AND/OR
# SOFTWARE, YOU UNEQUIVOCALLY ACCEPT, AND AGREE TO BE BOUND BY, ALL OF THE
# TERMS AND CONDITIONS OF THIS AGREEMENT. IF YOU DO NOT AGREE, DO NOT
# DOWNLOAD, INSTALL, COPY, DISTRIBUTE OR USE THE DATA FILES OR SOFTWARE.
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of data files and any associated documentation (the "Data Files") or
# software and any associated documentation (the "Software") to deal in the
# Data Files or Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, and/or sell
# copies of the Data Files or Software, and to permit persons to whom the
# Data Files or Software are furnished to do so, provided that either (a)
# this copyright and permission notice appear with all copies of the Data
# Files or Software, or (b) this copyright and permission notice appear in
# associated Documentation.
#
# THE DATA FILES AND SOFTWARE ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
# KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT OF
# THIRD PARTY RIGHTS.
#
# IN NO EVENT SHALL THE COPYRIGHT HOLDER OR HOLDERS INCLUDED IN THIS NOTICE
# BE LIABLE FOR ANY CLAIM, OR ANY SPECIAL INDIRECT OR CONSEQUENTIAL DAMAGES,
# OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS,
# WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION,
# ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THE DATA
# FILES OR SOFTWARE.
#
# Except as contained in this notice, the name of a copyright holder shall
# not be used in advertising or otherwise to promote the sale, use or other
# dealings in these Data Files or Software without prior written
# authorization of the copyright holder.
