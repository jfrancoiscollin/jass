# L3 Scan ceiling benchmark v1 — terminal scientific memo

- Verdict descriptif : `JASS_SEARCH_LARGE_HEADROOM_TO_SCAN_ESTABLISHED`
- Lecture roadmap : `JASS_SEARCH_SEMANTICS_PRIMARY`
- Statut : benchmark-only consommé ; aucune action de training/tuning/promotion autorisée.

## Provenance et contrat

- Scan : `Scan 3.1`, source `https://github.com/rhalbersma/scan`, commit `7aae17e7b7bfc47744601afb1ee7655e18983ce5`, tree `023eace16a90ec543b6b6174c79cfc42488a356e`.
- Binaire HOME SHA256 : `96b80c6aec1592f856a78ad7617ca6224b26be926800a6e37ede3b26f4e9cfa1` ; eval SHA256 : `0e7161c38af605f5e367f3f8fe17525d1c40db722714c68921971b386e58abba` ; ini SHA256 : `dc201a7debaf98bb869fb3d6b641adb219df71b0ea22004b2d9b6f51cdb69538`.
- Compilation : `-pthread -std=c++14 -fno-rtti -O2 -mpopcnt -flto -DNDEBUG` ; link `-pthread -O2 -flto` ; compilateur `g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`.
- Runtime Scan : `{"bb_size": 0, "book": false, "book_margin": 4, "book_ply": 4, "fresh_state": "new-game before every sibling/budget", "mode": "go analyze", "node_budget_contract": "exact requested N; stock last-info snapshot bounded by next 16-node poll", "ponder": false, "threads": 1, "tt_size": 24, "variant": "normal"}` ; tablebase Scan désactivée (`bb-size=0`) ; un thread/recherche, livre OFF, `new-game` avant chaque sibling/budget.
- Cohort identity SHA256 : `478abc0fe2fe1fcd8c2157f532ba796745c645ff4f03dac8fd21c2ff851f137e`.
- Snapshot exclusions runtime : cutoff `2026-08-29T13:34:07.134000+00:00`, control-plane `81d18eaeca31d94496f2e8c62f9e59a8246dddc9`, artifacts observables `1`.
- Bootstrap : 200000 resamples parent-cluster, seed 2026091303, CI percentile 95%.
- Artifacts : CURRICULUM `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`, D1 `e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49`, RF1 `0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b`, T3-A `16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2`
- Chaîne code : cohort figé `28e12fba0ead14def244ffc442b15937f65edc0e`, signaux statiques `4105121fe7bfd74888afaff701e10174192fa453`, scoring et readout `46623b26b8d684f5685475d81fbb36f215ba4ac2`.
- Readout brut publié : `r2:jass-data/runs/home-1660-l3-scan-ceiling-readout-v1/20260829T154532Z-46623b26` ; Markdown généré SHA256 `bd2785e72ad7694463e0e6fac055adf6af3fcbd4713aad02c9041518bbe57fec`. Le présent fichier ajoute uniquement l'interprétation descriptive ci-dessous ; les tables et valeurs générées sont inchangées.

CPU HOME (`lscpu`) :

```text
Architecture:                            x86_64
CPU op-mode(s):                          32-bit, 64-bit
Address sizes:                           48 bits physical, 48 bits virtual
Byte Order:                              Little Endian
CPU(s):                                  16
On-line CPU(s) list:                     0-15
Vendor ID:                               AuthenticAMD
Model name:                              AMD Ryzen 7 PRO 4750U with Radeon Graphics
CPU family:                              23
Model:                                   96
Thread(s) per core:                      2
Core(s) per socket:                      8
Socket(s):                               1
Stepping:                                1
BogoMIPS:                                3393.51
Flags:                                   fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse sse2 ht syscall nx mmxext fxsr_opt pdpe1gb rdtscp lm constant_tsc rep_good nopl xtopology tsc_reliable nonstop_tsc cpuid extd_apicid tsc_known_freq pni pclmulqdq ssse3 fma cx16 sse4_1 sse4_2 movbe popcnt aes xsave avx f16c rdrand hypervisor lahf_lm cmp_legacy svm cr8_legacy abm sse4a misalignsse 3dnowprefetch osvw topoext perfctr_core ssbd ibrs ibpb stibp vmmcall fsgsbase bmi1 avx2 smep bmi2 rdseed adx smap clflushopt clwb sha_ni xsaveopt xsavec xgetbv1 clzero xsaveerptr arat npt nrip_save tsc_scale vmcb_clean flushbyasid decodeassists pausefilter pfthreshold v_vmsave_vmload umip rdpid
Virtualization:                          AMD-V
Hypervisor vendor:                       Microsoft
Virtualization type:                     full
L1d cache:                               256 KiB (8 instances)
L1i cache:                               256 KiB (8 instances)
L2 cache:                                4 MiB (8 instances)
L3 cache:                                4 MiB (1 instance)
NUMA node(s):                            1
NUMA node0 CPU(s):                       0-15
Vulnerability Gather data sampling:      Not affected
Vulnerability Ghostwrite:                Not affected
Vulnerability Indirect target selection: Not affected
Vulnerability Itlb multihit:             Not affected
Vulnerability L1tf:                      Not affected
Vulnerability Mds:                       Not affected
Vulnerability Meltdown:                  Not affected
Vulnerability Mmio stale data:           Not affected
Vulnerability Old microcode:             Not affected
Vulnerability Reg file data sampling:    Not affected
Vulnerability Retbleed:                  Mitigation; untrained return thunk; SMT enabled with STIBP protection
Vulnerability Spec rstack overflow:      Vulnerable: Safe RET, no microcode
Vulnerability Spec store bypass:         Mitigation; Speculative Store Bypass disabled via prctl
Vulnerability Spectre v1:                Mitigation; usercopy/swapgs barriers and __user pointer sanitization
Vulnerability Spectre v2:                Mitigation; Retpolines; IBPB conditional; STIBP always-on; RSB filling; PBRSB-eIBRS Not affected; BHI Not affected
Vulnerability Srbds:                     Not affected
Vulnerability Tsa:                       Not affected
Vulnerability Tsx async abort:           Not affected
Vulnerability Vmscape:                   Not affected
```

## Ladders et compteurs de nœuds

| Stage | Budget | Lignes | Recherches | Terminal exact | TB exact | Nœuds demandés (recherches) | Nœuds reportés/snapshot | Sémantique |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Jass_BASE2000 | 1000 | 18400 | 18366 | 27 | 7 | 18366000 | 18160919 | exact_cap; node-stopped rows equal N; complete MAX_PLY rows may end below N |
| Jass_BASE2000 | 5000 | 18400 | 18366 | 27 | 7 | 91830000 | 90487973 | exact_cap; node-stopped rows equal N; complete MAX_PLY rows may end below N |
| Jass_BASE2000 | 50000 | 18400 | 18366 | 27 | 7 | 918300000 | 903672681 | exact_cap; node-stopped rows equal N; complete MAX_PLY rows may end below N |
| Jass_BASE2000 | 200000 | 18400 | 18366 | 27 | 7 | 3673200000 | 3613676149 | exact_cap; node-stopped rows equal N; complete MAX_PLY rows may end below N |
| Jass_DEEP512 | 1000000 | 4758 | 4742 | 11 | 5 | 4742000000 | 4649352119 | exact_cap; node-stopped rows equal N; complete MAX_PLY rows may end below N |
| Scan_BASE2000 | 1000 | 18400 | 18373 | 27 | 0 | 18373000 | 13596811 | exact requested N; last complete info is a progressive snapshot bounded by the next 16-node poll, not total consumed |
| Scan_BASE2000 | 5000 | 18400 | 18373 | 27 | 0 | 91865000 | 70885223 | exact requested N; last complete info is a progressive snapshot bounded by the next 16-node poll, not total consumed |
| Scan_BASE2000 | 50000 | 18400 | 18373 | 27 | 0 | 918650000 | 706245408 | exact requested N; last complete info is a progressive snapshot bounded by the next 16-node poll, not total consumed |
| Scan_BASE2000 | 200000 | 18400 | 18373 | 27 | 0 | 3674600000 | 2825538853 | exact requested N; last complete info is a progressive snapshot bounded by the next 16-node poll, not total consumed |
| Scan_DEEP512 | 1000000 | 4758 | 4747 | 11 | 0 | 4747000000 | 3553501484 | exact requested N; last complete info is a progressive snapshot bounded by the next 16-node poll, not total consumed |
| Scan_DEEP512 | 2000000 | 4758 | 4747 | 11 | 0 | 9494000000 | 7097924985 | exact requested N; last complete info is a progressive snapshot bounded by the next 16-node poll, not total consumed |
| Scan_ULTRA256 | 5000000 | 2445 | 2443 | 2 | 0 | 12215000000 | 8915367509 | exact requested N; last complete info is a progressive snapshot bounded by the next 16-node poll, not total consumed |

## Résultats globaux pairwise / top-hit

### BASE2000 vs Scan200k

| Signal | Pairwise primaire | Pairwise strict diag. | Top-hit primaire | Top-hit strict diag. | Kendall tau-b | Spearman rho |
|---|---:|---:|---:|---:|---:|---:|
| T0 | 0.5794 [0.5729, 0.5859]; brut 49776/85912 | 0.5749 [0.5686, 0.5811]; brut 52566/91435 | 0.2695 [0.2500, 0.2890]; brut 539/2000 | 0.2070 [0.1895, 0.2250]; brut 414/2000 | 0.1406 [0.1222, 0.1589] | 0.1820 [0.1613, 0.2026] |
| D1 | 0.5947 [0.5879, 0.6014]; brut 51090.5/85912 | 0.5897 [0.5832, 0.5962]; brut 53920/91435 | 0.2170 [0.1990, 0.2350]; brut 434/2000 | 0.1585 [0.1425, 0.1745]; brut 317/2000 | 0.1693 [0.1504, 0.1878] | 0.2258 [0.2045, 0.2468] |
| RF1 | 0.6437 [0.6367, 0.6507]; brut 55304.5/85912 | 0.6355 [0.6286, 0.6423]; brut 58105/91435 | 0.3070 [0.2870, 0.3275]; brut 614/2000 | 0.2540 [0.2350, 0.2730]; brut 508/2000 | 0.2847 [0.2658, 0.3035] | 0.3600 [0.3390, 0.3808] |
| T3-A | 0.6442 [0.6375, 0.6508]; brut 55342.5/85912 | 0.6359 [0.6293, 0.6424]; brut 58144/91435 | 0.3090 [0.2890, 0.3295]; brut 618/2000 | 0.2495 [0.2305, 0.2685]; brut 499/2000 | 0.2825 [0.2646, 0.3001] | 0.3567 [0.3367, 0.3764] |
| Jass1k | 0.7474 [0.7407, 0.7540]; brut 64208.5/85912 | 0.7433 [0.7364, 0.7501]; brut 67962/91435 | 0.4480 [0.4260, 0.4700]; brut 896/2000 | 0.4080 [0.3865, 0.4295]; brut 816/2000 | 0.4989 [0.4823, 0.5152] | 0.5908 [0.5731, 0.6081] |
| Jass5k | 0.7657 [0.7594, 0.7720]; brut 65783/85912 | 0.7625 [0.7560, 0.7690]; brut 69719/91435 | 0.4605 [0.4385, 0.4825]; brut 921/2000 | 0.4185 [0.3970, 0.4400]; brut 837/2000 | 0.5255 [0.5087, 0.5421] | 0.6180 [0.6003, 0.6353] |
| Jass50k | 0.7911 [0.7851, 0.7970]; brut 67962.5/85912 | 0.7882 [0.7820, 0.7943]; brut 72068/91435 | 0.5120 [0.4900, 0.5340]; brut 1024/2000 | 0.4740 [0.4520, 0.4960]; brut 948/2000 | 0.5868 [0.5715, 0.6019] | 0.6796 [0.6639, 0.6950] |
| Jass200k | 0.8031 [0.7971, 0.8089]; brut 68992.5/85912 | 0.8019 [0.7957, 0.8079]; brut 73320/91435 | 0.5450 [0.5230, 0.5670]; brut 1090/2000 | 0.5015 [0.4795, 0.5235]; brut 1003/2000 | 0.6114 [0.5960, 0.6264] | 0.7016 [0.6859, 0.7169] |
| Scan1k | 0.8383 [0.8330, 0.8436]; brut 72020.5/85912 | 0.8303 [0.8247, 0.8358]; brut 75917/91435 | 0.5725 [0.5510, 0.5940]; brut 1145/2000 | 0.5215 [0.4995, 0.5435]; brut 1043/2000 | 0.6699 [0.6563, 0.6832] | 0.7601 [0.7463, 0.7736] |
| Scan5k | 0.8606 [0.8556, 0.8655]; brut 73937/85912 | 0.8528 [0.8474, 0.8580]; brut 77975/91435 | 0.6075 [0.5860, 0.6290]; brut 1215/2000 | 0.5605 [0.5390, 0.5825]; brut 1121/2000 | 0.7219 [0.7096, 0.7338] | 0.8079 [0.7958, 0.8196] |
| Scan50k | 0.9018 [0.8979, 0.9056]; brut 77474.5/85912 | 0.8970 [0.8929, 0.9009]; brut 82015/91435 | 0.6945 [0.6740, 0.7145]; brut 1389/2000 | 0.6575 [0.6365, 0.6780]; brut 1315/2000 | 0.8133 [0.8034, 0.8227] | 0.8856 [0.8764, 0.8942] |

### DEEP512 vs Scan2M

| Signal | Pairwise primaire | Pairwise strict diag. | Top-hit primaire | Top-hit strict diag. | Kendall tau-b | Spearman rho |
|---|---:|---:|---:|---:|---:|---:|
| T0 | 0.5783 [0.5653, 0.5913]; brut 12897/22300 | 0.5721 [0.5597, 0.5845]; brut 13835/24182 | 0.3184 [0.2793, 0.3594]; brut 163/512 | 0.2461 [0.2090, 0.2832]; brut 126/512 | 0.1380 [0.1015, 0.1741] | 0.1850 [0.1440, 0.2254] |
| D1 | 0.5999 [0.5858, 0.6136]; brut 13377.5/22300 | 0.5922 [0.5787, 0.6055]; brut 14321/24182 | 0.2637 [0.2266, 0.3027]; brut 135/512 | 0.1953 [0.1621, 0.2305]; brut 100/512 | 0.1893 [0.1518, 0.2265] | 0.2456 [0.2027, 0.2879] |
| RF1 | 0.6511 [0.6361, 0.6657]; brut 14518.5/22300 | 0.6392 [0.6249, 0.6534]; brut 15458/24182 | 0.3184 [0.2793, 0.3594]; brut 163/512 | 0.2441 [0.2070, 0.2812]; brut 125/512 | 0.2843 [0.2460, 0.3222] | 0.3596 [0.3173, 0.4014] |
| T3-A | 0.6374 [0.6235, 0.6511]; brut 14214.5/22300 | 0.6260 [0.6125, 0.6394]; brut 15138/24182 | 0.3301 [0.2891, 0.3711]; brut 169/512 | 0.2520 [0.2148, 0.2891]; brut 129/512 | 0.2622 [0.2249, 0.2986] | 0.3351 [0.2934, 0.3757] |
| Jass1k | 0.7410 [0.7272, 0.7547]; brut 16524/22300 | 0.7359 [0.7216, 0.7500]; brut 17795/24182 | 0.4668 [0.4238, 0.5098]; brut 239/512 | 0.4219 [0.3789, 0.4648]; brut 216/512 | 0.5045 [0.4736, 0.5348] | 0.5955 [0.5625, 0.6275] |
| Jass5k | 0.7683 [0.7561, 0.7803]; brut 17134/22300 | 0.7635 [0.7503, 0.7765]; brut 18462/24182 | 0.4805 [0.4375, 0.5234]; brut 246/512 | 0.4414 [0.3984, 0.4844]; brut 226/512 | 0.5308 [0.4986, 0.5621] | 0.6233 [0.5892, 0.6560] |
| Jass50k | 0.7863 [0.7735, 0.7987]; brut 17534/22300 | 0.7823 [0.7690, 0.7954]; brut 18918/24182 | 0.5293 [0.4863, 0.5723]; brut 271/512 | 0.4805 [0.4375, 0.5234]; brut 246/512 | 0.5779 [0.5475, 0.6073] | 0.6684 [0.6363, 0.6991] |
| Jass200k | 0.7987 [0.7867, 0.8104]; brut 17810.5/22300 | 0.7969 [0.7845, 0.8093]; brut 19271/24182 | 0.5371 [0.4941, 0.5801]; brut 275/512 | 0.4941 [0.4512, 0.5371]; brut 253/512 | 0.6018 [0.5714, 0.6312] | 0.6905 [0.6588, 0.7210] |
| Jass1M | 0.8091 [0.7971, 0.8209]; brut 18044/22300 | 0.8081 [0.7951, 0.8207]; brut 19541/24182 | 0.5156 [0.4727, 0.5586]; brut 264/512 | 0.4805 [0.4375, 0.5234]; brut 246/512 | 0.6169 [0.5851, 0.6473] | 0.7041 [0.6712, 0.7355] |
| Scan1k | 0.8301 [0.8193, 0.8407]; brut 18511.5/22300 | 0.8201 [0.8086, 0.8312]; brut 19831/24182 | 0.5449 [0.5020, 0.5879]; brut 279/512 | 0.4961 [0.4531, 0.5391]; brut 254/512 | 0.6522 [0.6246, 0.6786] | 0.7444 [0.7161, 0.7711] |
| Scan5k | 0.8456 [0.8350, 0.8558]; brut 18857/22300 | 0.8344 [0.8227, 0.8457]; brut 20178/24182 | 0.5938 [0.5508, 0.6367]; brut 304/512 | 0.5469 [0.5039, 0.5898]; brut 280/512 | 0.6994 [0.6764, 0.7215] | 0.7921 [0.7694, 0.8135] |
| Scan50k | 0.8775 [0.8688, 0.8860]; brut 19569/22300 | 0.8705 [0.8606, 0.8800]; brut 21050/24182 | 0.6738 [0.6328, 0.7148]; brut 345/512 | 0.6270 [0.5840, 0.6680]; brut 321/512 | 0.7663 [0.7437, 0.7873] | 0.8508 [0.8294, 0.8702] |
| Scan200k | 0.8979 [0.8898, 0.9058]; brut 20023.5/22300 | 0.8923 [0.8832, 0.9011]; brut 21578/24182 | 0.7324 [0.6934, 0.7695]; brut 375/512 | 0.6895 [0.6484, 0.7285]; brut 353/512 | 0.8117 [0.7921, 0.8299] | 0.8869 [0.8690, 0.9026] |
| Scan1M | 0.9329 [0.9273, 0.9384]; brut 20804/22300 | 0.9280 [0.9216, 0.9341]; brut 22440/24182 | 0.7598 [0.7227, 0.7969]; brut 389/512 | 0.7266 [0.6875, 0.7656]; brut 372/512 | 0.8809 [0.8668, 0.8936] | 0.9366 [0.9245, 0.9465] |

### ULTRA256 vs Scan5M

| Signal | Pairwise primaire | Pairwise strict diag. | Top-hit primaire | Top-hit strict diag. | Kendall tau-b | Spearman rho |
|---|---:|---:|---:|---:|---:|---:|
| T0 | 0.5687 [0.5499, 0.5872]; brut 6579/11569 | 0.5629 [0.5451, 0.5805]; brut 7084/12585 | 0.2773 [0.2227, 0.3320]; brut 71/256 | 0.1953 [0.1484, 0.2461]; brut 50/256 | 0.0845 [0.0346, 0.1336] | 0.1253 [0.0680, 0.1818] |
| D1 | 0.5997 [0.5810, 0.6179]; brut 6938/11569 | 0.5921 [0.5744, 0.6094]; brut 7451/12585 | 0.2695 [0.2148, 0.3242]; brut 69/256 | 0.1836 [0.1367, 0.2305]; brut 47/256 | 0.1878 [0.1386, 0.2360] | 0.2510 [0.1945, 0.3062] |
| RF1 | 0.6466 [0.6264, 0.6661]; brut 7480/11569 | 0.6346 [0.6154, 0.6533]; brut 7986/12585 | 0.2812 [0.2266, 0.3359]; brut 72/256 | 0.1953 [0.1484, 0.2461]; brut 50/256 | 0.2731 [0.2221, 0.3229] | 0.3506 [0.2934, 0.4061] |
| T3-A | 0.6264 [0.6052, 0.6470]; brut 7247/11569 | 0.6122 [0.5913, 0.6327]; brut 7705/12585 | 0.2930 [0.2383, 0.3477]; brut 75/256 | 0.2227 [0.1719, 0.2734]; brut 57/256 | 0.2344 [0.1835, 0.2841] | 0.3005 [0.2425, 0.3571] |
| Jass1k | 0.7398 [0.7201, 0.7591]; brut 8558.5/11569 | 0.7360 [0.7149, 0.7568]; brut 9263/12585 | 0.4688 [0.4062, 0.5312]; brut 120/256 | 0.4180 [0.3594, 0.4805]; brut 107/256 | 0.4804 [0.4344, 0.5245] | 0.5704 [0.5205, 0.6179] |
| Jass5k | 0.7678 [0.7503, 0.7850]; brut 8882.5/11569 | 0.7639 [0.7446, 0.7828]; brut 9614/12585 | 0.4609 [0.3984, 0.5234]; brut 118/256 | 0.4141 [0.3555, 0.4727]; brut 106/256 | 0.5122 [0.4643, 0.5576] | 0.6033 [0.5520, 0.6518] |
| Jass50k | 0.7772 [0.7585, 0.7952]; brut 8992/11569 | 0.7752 [0.7556, 0.7941]; brut 9756/12585 | 0.4336 [0.3750, 0.4961]; brut 111/256 | 0.3945 [0.3359, 0.4531]; brut 101/256 | 0.5255 [0.4763, 0.5721] | 0.6186 [0.5655, 0.6686] |
| Jass200k | 0.7923 [0.7747, 0.8094]; brut 9166.5/11569 | 0.7897 [0.7709, 0.8080]; brut 9938/12585 | 0.4688 [0.4062, 0.5312]; brut 120/256 | 0.4258 [0.3672, 0.4883]; brut 109/256 | 0.5616 [0.5136, 0.6072] | 0.6473 [0.5959, 0.6957] |
| Jass1M | 0.8019 [0.7835, 0.8196]; brut 9277/11569 | 0.8009 [0.7815, 0.8197]; brut 10079/12585 | 0.4961 [0.4336, 0.5586]; brut 127/256 | 0.4609 [0.3984, 0.5234]; brut 118/256 | 0.5711 [0.5204, 0.6187] | 0.6565 [0.6023, 0.7071] |
| Scan1k | 0.8260 [0.8110, 0.8405]; brut 9555.5/11569 | 0.8192 [0.8028, 0.8351]; brut 10310/12585 | 0.5039 [0.4414, 0.5664]; brut 129/256 | 0.4336 [0.3750, 0.4922]; brut 111/256 | 0.6388 [0.5981, 0.6765] | 0.7295 [0.6867, 0.7685] |
| Scan5k | 0.8398 [0.8238, 0.8549]; brut 9715.5/11569 | 0.8332 [0.8158, 0.8498]; brut 10486/12585 | 0.5781 [0.5156, 0.6367]; brut 148/256 | 0.5234 [0.4609, 0.5859]; brut 134/256 | 0.6724 [0.6350, 0.7074] | 0.7661 [0.7278, 0.8012] |
| Scan50k | 0.8681 [0.8545, 0.8810]; brut 10043/11569 | 0.8630 [0.8484, 0.8769]; brut 10861/12585 | 0.6289 [0.5703, 0.6875]; brut 161/256 | 0.5664 [0.5039, 0.6250]; brut 145/256 | 0.7326 [0.6939, 0.7678] | 0.8212 [0.7832, 0.8548] |
| Scan200k | 0.8877 [0.8757, 0.8992]; brut 10269.5/11569 | 0.8832 [0.8698, 0.8960]; brut 11115/12585 | 0.6680 [0.6094, 0.7266]; brut 171/256 | 0.6133 [0.5547, 0.6719]; brut 157/256 | 0.7892 [0.7600, 0.8159] | 0.8697 [0.8425, 0.8934] |
| Scan1M | 0.9114 [0.9023, 0.9202]; brut 10544/11569 | 0.9074 [0.8968, 0.9174]; brut 11419/12585 | 0.6875 [0.6289, 0.7422]; brut 176/256 | 0.6602 [0.6016, 0.7188]; brut 169/256 | 0.8219 [0.7912, 0.8485] | 0.8935 [0.8644, 0.9174] |
| Scan2M | 0.9259 [0.9169, 0.9344]; brut 10712/11569 | 0.9228 [0.9129, 0.9321]; brut 11613/12585 | 0.7422 [0.6875, 0.7930]; brut 190/256 | 0.7070 [0.6484, 0.7617]; brut 181/256 | 0.8547 [0.8253, 0.8795] | 0.9147 [0.8866, 0.9371] |

## Bottleneck DEEP512 / Scan2M

| Quantité | Point et CI95 |
|---|---:|
| t3_a_minus_t0 | 0.0591 [0.0456, 0.0724] |
| jass200k_minus_t3_a | 0.1613 [0.1465, 0.1762] |
| jass1m_minus_jass200k | 0.0105 [0.0041, 0.0169] |
| scan200k_minus_jass200k | 0.0992 [0.0898, 0.1089] |
| scan1m_minus_jass1m | 0.1238 [0.1131, 0.1347] |
| t3_a_fraction_of_t0_to_reference | 0.1401 [0.1096, 0.1697] |
| one_minus_jass200k | 0.2013 [0.1896, 0.2133] |
| one_minus_jass1m | 0.1909 [0.1791, 0.2029] |

## Convergence Scan

| Comparaison | Accuracy et CI95 |
|---|---:|
| DEEP512_Scan1M_vs_Scan2M | 0.9329 [0.9273, 0.9384] |
| ULTRA256_Scan1M_vs_Scan5M | 0.9114 [0.9023, 0.9202] |
| ULTRA256_Scan2M_vs_Scan5M | 0.9259 [0.9169, 0.9344] |

## Equivalent descriptif Scan-nodes (ULTRA256 / Scan5M)

| Signal | Catégorie | Equivalent point | CI95 fini | <1k | >2M | plateau |
|---|---|---:|---:|---:|---:|---:|
| T0 | below_1k | NA | NA | 1.0000 | 0.0000 | 0.0000 |
| D1 | below_1k | NA | NA | 1.0000 | 0.0000 | 0.0000 |
| RF1 | below_1k | NA | NA | 1.0000 | 0.0000 | 0.0000 |
| T3-A | below_1k | NA | NA | 1.0000 | 0.0000 | 0.0000 |
| Jass1k | below_1k | NA | NA | 1.0000 | 0.0000 | 0.0000 |
| Jass5k | below_1k | NA | NA | 1.0000 | 0.0000 | 0.0000 |
| Jass50k | below_1k | NA | NA | 1.0000 | 0.0000 | 0.0000 |
| Jass200k | below_1k | NA | [1230.3384335714716, 1242.7799029295234] | 1.0000 | 0.0000 | 0.0000 |
| Jass1M | below_1k | NA | [1003.2534501379714, 2288.7051852918967] | 0.9988 | 0.0000 | 0.0000 |
| Scan1k | finite | 1000.0 | [1000.0, 1000.0] | 0.0000 | 0.0000 | 0.0001 |
| Scan5k | finite | 5000.0 | [5000.0, 5000.0] | 0.0019 | 0.0000 | 0.0001 |
| Scan50k | finite | 50000.0 | [50000.0, 50000.0] | 0.0000 | 0.0000 | 0.0000 |
| Scan200k | finite | 200000.0 | [200000.0, 200000.0] | 0.0000 | 0.0000 | 0.0000 |
| Scan1M | finite | 1000000.0 | [1000000.0, 1000000.0] | 0.0000 | 0.0000 | 0.0000 |
| Scan2M | finite | 2000000.0 | [2000000.0, 2000000.0] | 0.0000 | 0.0000 | 0.0000 |

## Practical headroom recovery (ULTRA256)

| Signal | Recovery et CI95 |
|---|---:|
| D1 | 0.0869 [0.0260, 0.1446] |
| RF1 | 0.2180 [0.1582, 0.2737] |
| T3-A | 0.1616 [0.1079, 0.2121] |
| Jass1k | 0.4789 [0.4281, 0.5272] |
| Jass50k | 0.5838 [0.5371, 0.6278] |
| Jass200k | 0.6261 [0.5824, 0.6671] |
| Jass1M | 0.6528 [0.6071, 0.6961] |

## Interprétation descriptive et implications roadmap

- T3-A n'est pas proche de la référence profonde pratique : sur DEEP512, son pairwise est `0.6374 [0.6235, 0.6511]` contre Scan2M et il ne récupère que `0.1401 [0.1096, 0.1697]` du headroom T0 -> référence. Sur ULTRA256, sa recovery pratique est `0.1616 [0.1079, 0.2121]`.
- Le headroom student/distillation est réel : Jass200k dépasse T3-A de `0.1613 [0.1465, 0.1762]` sur DEEP512. Cela ne suffit toutefois pas à faire de la seule distillation le bottleneck principal, car le teacher/search Jass reste lui-même très éloigné de Scan.
- Jass200k n'est pas proche du practical Scan ceiling : `0.7987 [0.7867, 0.8104]` contre Scan2M. À budget nominal identique, Scan200k le dépasse de `0.0992 [0.0898, 0.1089]`.
- Augmenter seulement le budget Jass ferme peu de cet écart : Jass1M ne gagne que `0.0105 [0.0041, 0.0169]` sur Jass200k, soit `5.20%` du gap descriptif restant, et reste `0.1238 [0.1131, 0.1347]` sous Scan1M au même budget nominal.
- La convergence interne de Scan est forte mais incomplète : Scan1M vs Scan2M vaut `0.9329 [0.9273, 0.9384]` et Scan2M vs Scan5M `0.9259 [0.9169, 0.9344]`. Scan5M reste donc une `external_deep_reference` / `practical_scan_ceiling` et ne constitue pas l'optimum mathématique.
- Lecture roadmap descriptive : le headroom principal observé pointe vers les semantics de search/eval de Jass relativement à Scan (`JASS_SEARCH_SEMANTICS_PRIMARY`), avec la distillation/student comme headroom secondaire mesurable. Une éventuelle action d'ingénierie exige une nouvelle prereg séparée ; cette campagne n'autorise ni feature selection, ni tuning, ni calibration, ni promotion.

## Ventilations préenregistrées

### BASE2000

| Strate | Signal | Parents | Pairs totaux | Pairs comparables | Ties référence | Pairwise | Top-hit |
|---|---|---:|---:|---:|---:|---:|---:|
| phase:P0 | T0 | 500 | 27530 | 26720 | 810 | 0.6216 [0.6109, 0.6323]; brut 16609/26720 | 0.2440 [0.2060, 0.2820]; brut 122/500 |
| phase:P0 | D1 | 500 | 27530 | 26720 | 810 | 0.6194 [0.6075, 0.6312]; brut 16551/26720 | 0.1700 [0.1380, 0.2040]; brut 85/500 |
| phase:P0 | RF1 | 500 | 27530 | 26720 | 810 | 0.6719 [0.6605, 0.6832]; brut 17954/26720 | 0.2420 [0.2040, 0.2800]; brut 121/500 |
| phase:P0 | T3-A | 500 | 27530 | 26720 | 810 | 0.6701 [0.6591, 0.6809]; brut 17904/26720 | 0.2400 [0.2040, 0.2780]; brut 120/500 |
| phase:P0 | Jass1k | 500 | 27530 | 26720 | 810 | 0.7896 [0.7800, 0.7991]; brut 21098.5/26720 | 0.4240 [0.3800, 0.4680]; brut 212/500 |
| phase:P0 | Jass5k | 500 | 27530 | 26720 | 810 | 0.8068 [0.7974, 0.8160]; brut 21558/26720 | 0.4240 [0.3820, 0.4680]; brut 212/500 |
| phase:P0 | Jass50k | 500 | 27530 | 26720 | 810 | 0.8256 [0.8168, 0.8343]; brut 22060.5/26720 | 0.4980 [0.4540, 0.5420]; brut 249/500 |
| phase:P0 | Jass200k | 500 | 27530 | 26720 | 810 | 0.8380 [0.8299, 0.8461]; brut 22392/26720 | 0.5180 [0.4740, 0.5620]; brut 259/500 |
| phase:P0 | Scan1k | 500 | 27530 | 26720 | 810 | 0.8796 [0.8735, 0.8857]; brut 23503.5/26720 | 0.6060 [0.5620, 0.6480]; brut 303/500 |
| phase:P0 | Scan5k | 500 | 27530 | 26720 | 810 | 0.8988 [0.8930, 0.9045]; brut 24016.5/26720 | 0.6400 [0.5980, 0.6820]; brut 320/500 |
| phase:P0 | Scan50k | 500 | 27530 | 26720 | 810 | 0.9269 [0.9222, 0.9316]; brut 24768/26720 | 0.6680 [0.6260, 0.7100]; brut 334/500 |
| phase:P1 | T0 | 500 | 31015 | 30311 | 704 | 0.5728 [0.5618, 0.5838]; brut 17362.5/30311 | 0.1720 [0.1400, 0.2060]; brut 86/500 |
| phase:P1 | D1 | 500 | 31015 | 30311 | 704 | 0.6046 [0.5939, 0.6152]; brut 18326/30311 | 0.1320 [0.1040, 0.1620]; brut 66/500 |
| phase:P1 | RF1 | 500 | 31015 | 30311 | 704 | 0.6333 [0.6216, 0.6449]; brut 19197/30311 | 0.1920 [0.1580, 0.2280]; brut 96/500 |
| phase:P1 | T3-A | 500 | 31015 | 30311 | 704 | 0.6416 [0.6303, 0.6527]; brut 19447/30311 | 0.2040 [0.1700, 0.2400]; brut 102/500 |
| phase:P1 | Jass1k | 500 | 31015 | 30311 | 704 | 0.7383 [0.7275, 0.7490]; brut 22379/30311 | 0.3360 [0.2940, 0.3780]; brut 168/500 |
| phase:P1 | Jass5k | 500 | 31015 | 30311 | 704 | 0.7529 [0.7423, 0.7634]; brut 22821.5/30311 | 0.3760 [0.3340, 0.4180]; brut 188/500 |
| phase:P1 | Jass50k | 500 | 31015 | 30311 | 704 | 0.7814 [0.7710, 0.7917]; brut 23686/30311 | 0.4040 [0.3620, 0.4480]; brut 202/500 |
| phase:P1 | Jass200k | 500 | 31015 | 30311 | 704 | 0.7945 [0.7846, 0.8043]; brut 24083/30311 | 0.4500 [0.4060, 0.4940]; brut 225/500 |
| phase:P1 | Scan1k | 500 | 31015 | 30311 | 704 | 0.8418 [0.8339, 0.8496]; brut 25516.5/30311 | 0.4740 [0.4300, 0.5180]; brut 237/500 |
| phase:P1 | Scan5k | 500 | 31015 | 30311 | 704 | 0.8582 [0.8506, 0.8656]; brut 26013/30311 | 0.4880 [0.4440, 0.5320]; brut 244/500 |
| phase:P1 | Scan50k | 500 | 31015 | 30311 | 704 | 0.8959 [0.8897, 0.9019]; brut 27155.5/30311 | 0.5880 [0.5440, 0.6320]; brut 294/500 |
| phase:P2 | T0 | 500 | 19862 | 18480 | 1382 | 0.5498 [0.5368, 0.5628]; brut 10161/18480 | 0.2480 [0.2100, 0.2860]; brut 124/500 |
| phase:P2 | D1 | 500 | 19862 | 18480 | 1382 | 0.5656 [0.5499, 0.5811]; brut 10452/18480 | 0.2200 [0.1840, 0.2560]; brut 110/500 |
| phase:P2 | RF1 | 500 | 19862 | 18480 | 1382 | 0.6227 [0.6062, 0.6391]; brut 11508/18480 | 0.2900 [0.2500, 0.3300]; brut 145/500 |
| phase:P2 | T3-A | 500 | 19862 | 18480 | 1382 | 0.6243 [0.6087, 0.6397]; brut 11537/18480 | 0.3180 [0.2780, 0.3600]; brut 159/500 |
| phase:P2 | Jass1k | 500 | 19862 | 18480 | 1382 | 0.7095 [0.6938, 0.7250]; brut 13112/18480 | 0.4180 [0.3760, 0.4620]; brut 209/500 |
| phase:P2 | Jass5k | 500 | 19862 | 18480 | 1382 | 0.7390 [0.7250, 0.7528]; brut 13656.5/18480 | 0.4420 [0.3980, 0.4860]; brut 221/500 |
| phase:P2 | Jass50k | 500 | 19862 | 18480 | 1382 | 0.7697 [0.7561, 0.7831]; brut 14223.5/18480 | 0.5000 [0.4560, 0.5440]; brut 250/500 |
| phase:P2 | Jass200k | 500 | 19862 | 18480 | 1382 | 0.7875 [0.7738, 0.8011]; brut 14553.5/18480 | 0.5520 [0.5080, 0.5960]; brut 276/500 |
| phase:P2 | Scan1k | 500 | 19862 | 18480 | 1382 | 0.7957 [0.7830, 0.8081]; brut 14704/18480 | 0.5220 [0.4780, 0.5660]; brut 261/500 |
| phase:P2 | Scan5k | 500 | 19862 | 18480 | 1382 | 0.8265 [0.8149, 0.8377]; brut 15274/18480 | 0.5740 [0.5300, 0.6180]; brut 287/500 |
| phase:P2 | Scan50k | 500 | 19862 | 18480 | 1382 | 0.8782 [0.8687, 0.8874]; brut 16228.5/18480 | 0.7040 [0.6640, 0.7440]; brut 352/500 |
| phase:P3 | T0 | 500 | 13028 | 10401 | 2627 | 0.5426 [0.5236, 0.5617]; brut 5643.5/10401 | 0.4140 [0.3700, 0.4580]; brut 207/500 |
| phase:P3 | D1 | 500 | 13028 | 10401 | 2627 | 0.5539 [0.5348, 0.5729]; brut 5761.5/10401 | 0.3460 [0.3040, 0.3880]; brut 173/500 |
| phase:P3 | RF1 | 500 | 13028 | 10401 | 2627 | 0.6389 [0.6184, 0.6596]; brut 6645.5/10401 | 0.5040 [0.4600, 0.5480]; brut 252/500 |
| phase:P3 | T3-A | 500 | 13028 | 10401 | 2627 | 0.6206 [0.6019, 0.6392]; brut 6454.5/10401 | 0.4740 [0.4300, 0.5180]; brut 237/500 |
| phase:P3 | Jass1k | 500 | 13028 | 10401 | 2627 | 0.7325 [0.7107, 0.7538]; brut 7619/10401 | 0.6140 [0.5720, 0.6560]; brut 307/500 |
| phase:P3 | Jass5k | 500 | 13028 | 10401 | 2627 | 0.7448 [0.7250, 0.7644]; brut 7747/10401 | 0.6000 [0.5580, 0.6420]; brut 300/500 |
| phase:P3 | Jass50k | 500 | 13028 | 10401 | 2627 | 0.7684 [0.7507, 0.7859]; brut 7992.5/10401 | 0.6460 [0.6040, 0.6880]; brut 323/500 |
| phase:P3 | Jass200k | 500 | 13028 | 10401 | 2627 | 0.7657 [0.7465, 0.7847]; brut 7964/10401 | 0.6600 [0.6180, 0.7020]; brut 330/500 |
| phase:P3 | Scan1k | 500 | 13028 | 10401 | 2627 | 0.7977 [0.7782, 0.8171]; brut 8296.5/10401 | 0.6880 [0.6480, 0.7280]; brut 344/500 |
| phase:P3 | Scan5k | 500 | 13028 | 10401 | 2627 | 0.8301 [0.8113, 0.8484]; brut 8633.5/10401 | 0.7280 [0.6880, 0.7660]; brut 364/500 |
| phase:P3 | Scan50k | 500 | 13028 | 10401 | 2627 | 0.8963 [0.8825, 0.9093]; brut 9322.5/10401 | 0.8180 [0.7840, 0.8520]; brut 409/500 |
| colour:white | T0 | 993 | 44136 | 41515 | 2621 | 0.5740 [0.5645, 0.5833]; brut 23828.5/41515 | 0.2548 [0.2276, 0.2820]; brut 253/993 |
| colour:white | D1 | 993 | 44136 | 41515 | 2621 | 0.5933 [0.5834, 0.6033]; brut 24632.5/41515 | 0.2135 [0.1883, 0.2397]; brut 212/993 |
| colour:white | RF1 | 993 | 44136 | 41515 | 2621 | 0.6409 [0.6304, 0.6513]; brut 26606.5/41515 | 0.3031 [0.2749, 0.3323]; brut 301/993 |
| colour:white | T3-A | 993 | 44136 | 41515 | 2621 | 0.6356 [0.6260, 0.6452]; brut 26387.5/41515 | 0.2931 [0.2649, 0.3212]; brut 291/993 |
| colour:white | Jass1k | 993 | 44136 | 41515 | 2621 | 0.7477 [0.7377, 0.7576]; brut 31040/41515 | 0.4411 [0.4099, 0.4723]; brut 438/993 |
| colour:white | Jass5k | 993 | 44136 | 41515 | 2621 | 0.7639 [0.7547, 0.7731]; brut 31714.5/41515 | 0.4512 [0.4199, 0.4824]; brut 448/993 |
| colour:white | Jass50k | 993 | 44136 | 41515 | 2621 | 0.7871 [0.7783, 0.7958]; brut 32676/41515 | 0.4914 [0.4602, 0.5227]; brut 488/993 |
| colour:white | Jass200k | 993 | 44136 | 41515 | 2621 | 0.7993 [0.7907, 0.8078]; brut 33181.5/41515 | 0.5206 [0.4894, 0.5519]; brut 517/993 |
| colour:white | Scan1k | 993 | 44136 | 41515 | 2621 | 0.8400 [0.8325, 0.8473]; brut 34872.5/41515 | 0.5690 [0.5378, 0.6002]; brut 565/993 |
| colour:white | Scan5k | 993 | 44136 | 41515 | 2621 | 0.8609 [0.8540, 0.8676]; brut 35740/41515 | 0.5982 [0.5670, 0.6284]; brut 594/993 |
| colour:white | Scan50k | 993 | 44136 | 41515 | 2621 | 0.9029 [0.8975, 0.9082]; brut 37485/41515 | 0.6999 [0.6717, 0.7281]; brut 695/993 |
| colour:black | T0 | 1007 | 47299 | 44397 | 2902 | 0.5844 [0.5755, 0.5934]; brut 25947.5/44397 | 0.2840 [0.2562, 0.3118]; brut 286/1007 |
| colour:black | D1 | 1007 | 47299 | 44397 | 2902 | 0.5959 [0.5866, 0.6051]; brut 26458/44397 | 0.2205 [0.1946, 0.2463]; brut 222/1007 |
| colour:black | RF1 | 1007 | 47299 | 44397 | 2902 | 0.6464 [0.6369, 0.6558]; brut 28698/44397 | 0.3108 [0.2820, 0.3396]; brut 313/1007 |
| colour:black | T3-A | 1007 | 47299 | 44397 | 2902 | 0.6522 [0.6428, 0.6615]; brut 28955/44397 | 0.3247 [0.2959, 0.3535]; brut 327/1007 |
| colour:black | Jass1k | 1007 | 47299 | 44397 | 2902 | 0.7471 [0.7380, 0.7560]; brut 33168.5/44397 | 0.4548 [0.4240, 0.4856]; brut 458/1007 |
| colour:black | Jass5k | 1007 | 47299 | 44397 | 2902 | 0.7674 [0.7586, 0.7760]; brut 34068.5/44397 | 0.4697 [0.4389, 0.5005]; brut 473/1007 |
| colour:black | Jass50k | 1007 | 47299 | 44397 | 2902 | 0.7948 [0.7866, 0.8028]; brut 35286.5/44397 | 0.5323 [0.5015, 0.5631]; brut 536/1007 |
| colour:black | Jass200k | 1007 | 47299 | 44397 | 2902 | 0.8066 [0.7984, 0.8146]; brut 35811/44397 | 0.5690 [0.5382, 0.5988]; brut 573/1007 |
| colour:black | Scan1k | 1007 | 47299 | 44397 | 2902 | 0.8367 [0.8290, 0.8441]; brut 37148/44397 | 0.5760 [0.5452, 0.6068]; brut 580/1007 |
| colour:black | Scan5k | 1007 | 47299 | 44397 | 2902 | 0.8604 [0.8532, 0.8673]; brut 38197/44397 | 0.6167 [0.5869, 0.6465]; brut 621/1007 |
| colour:black | Scan50k | 1007 | 47299 | 44397 | 2902 | 0.9007 [0.8952, 0.9061]; brut 39989.5/44397 | 0.6892 [0.6604, 0.7170]; brut 694/1007 |
| branching:2..4 | T0 | 353 | 810 | 541 | 269 | 0.5305 [0.4815, 0.5802]; brut 287/541 | 0.6487 [0.5977, 0.6969]; brut 229/353 |
| branching:2..4 | D1 | 353 | 810 | 541 | 269 | 0.5499 [0.4973, 0.6020]; brut 297.5/541 | 0.6374 [0.5864, 0.6884]; brut 225/353 |
| branching:2..4 | RF1 | 353 | 810 | 541 | 269 | 0.6312 [0.5794, 0.6818]; brut 341.5/541 | 0.6969 [0.6487, 0.7450]; brut 246/353 |
| branching:2..4 | T3-A | 353 | 810 | 541 | 269 | 0.6534 [0.6046, 0.7009]; brut 353.5/541 | 0.7167 [0.6686, 0.7620]; brut 253/353 |
| branching:2..4 | Jass1k | 353 | 810 | 541 | 269 | 0.7588 [0.7148, 0.8010]; brut 410.5/541 | 0.7904 [0.7479, 0.8329]; brut 279/353 |
| branching:2..4 | Jass5k | 353 | 810 | 541 | 269 | 0.7523 [0.7092, 0.7943]; brut 407/541 | 0.7875 [0.7450, 0.8300]; brut 278/353 |
| branching:2..4 | Jass50k | 353 | 810 | 541 | 269 | 0.8207 [0.7809, 0.8588]; brut 444/541 | 0.8499 [0.8102, 0.8867]; brut 300/353 |
| branching:2..4 | Jass200k | 353 | 810 | 541 | 269 | 0.8170 [0.7757, 0.8562]; brut 442/541 | 0.8612 [0.8244, 0.8952]; brut 304/353 |
| branching:2..4 | Scan1k | 353 | 810 | 541 | 269 | 0.8281 [0.7908, 0.8639]; brut 448/541 | 0.8612 [0.8244, 0.8952]; brut 304/353 |
| branching:2..4 | Scan5k | 353 | 810 | 541 | 269 | 0.8706 [0.8352, 0.9048]; brut 471/541 | 0.8867 [0.8527, 0.9178]; brut 313/353 |
| branching:2..4 | Scan50k | 353 | 810 | 541 | 269 | 0.9113 [0.8776, 0.9423]; brut 493/541 | 0.9320 [0.9037, 0.9575]; brut 329/353 |
| branching:5..8 | T0 | 368 | 7065 | 6862 | 203 | 0.5267 [0.5086, 0.5445]; brut 3614/6862 | 0.2364 [0.1929, 0.2799]; brut 87/368 |
| branching:5..8 | D1 | 368 | 7065 | 6862 | 203 | 0.5810 [0.5633, 0.5987]; brut 3987/6862 | 0.1576 [0.1223, 0.1957]; brut 58/368 |
| branching:5..8 | RF1 | 368 | 7065 | 6862 | 203 | 0.6791 [0.6583, 0.6997]; brut 4660/6862 | 0.3261 [0.2799, 0.3750]; brut 120/368 |
| branching:5..8 | T3-A | 368 | 7065 | 6862 | 203 | 0.6419 [0.6240, 0.6597]; brut 4405/6862 | 0.2799 [0.2337, 0.3261]; brut 103/368 |
| branching:5..8 | Jass1k | 368 | 7065 | 6862 | 203 | 0.7364 [0.7187, 0.7536]; brut 5053/6862 | 0.4049 [0.3560, 0.4565]; brut 149/368 |
| branching:5..8 | Jass5k | 368 | 7065 | 6862 | 203 | 0.7526 [0.7353, 0.7694]; brut 5164/6862 | 0.3995 [0.3505, 0.4511]; brut 147/368 |
| branching:5..8 | Jass50k | 368 | 7065 | 6862 | 203 | 0.7664 [0.7503, 0.7819]; brut 5259/6862 | 0.4592 [0.4076, 0.5109]; brut 169/368 |
| branching:5..8 | Jass200k | 368 | 7065 | 6862 | 203 | 0.7762 [0.7604, 0.7916]; brut 5326.5/6862 | 0.4647 [0.4130, 0.5163]; brut 171/368 |
| branching:5..8 | Scan1k | 368 | 7065 | 6862 | 203 | 0.8108 [0.7959, 0.8252]; brut 5564/6862 | 0.4946 [0.4429, 0.5462]; brut 182/368 |
| branching:5..8 | Scan5k | 368 | 7065 | 6862 | 203 | 0.8406 [0.8276, 0.8533]; brut 5768/6862 | 0.5734 [0.5217, 0.6250]; brut 211/368 |
| branching:5..8 | Scan50k | 368 | 7065 | 6862 | 203 | 0.8976 [0.8881, 0.9068]; brut 6159.5/6862 | 0.7011 [0.6549, 0.7473]; brut 258/368 |
| branching:9..12 | T0 | 849 | 43998 | 41912 | 2086 | 0.5883 [0.5797, 0.5969]; brut 24657.5/41912 | 0.1849 [0.1590, 0.2120]; brut 157/849 |
| branching:9..12 | D1 | 849 | 43998 | 41912 | 2086 | 0.5951 [0.5858, 0.6043]; brut 24942/41912 | 0.1190 [0.0978, 0.1413]; brut 101/849 |
| branching:9..12 | RF1 | 849 | 43998 | 41912 | 2086 | 0.6449 [0.6354, 0.6543]; brut 27028/41912 | 0.1932 [0.1673, 0.2203]; brut 164/849 |
| branching:9..12 | T3-A | 849 | 43998 | 41912 | 2086 | 0.6505 [0.6417, 0.6593]; brut 27265/41912 | 0.2132 [0.1861, 0.2415]; brut 181/849 |
| branching:9..12 | Jass1k | 849 | 43998 | 41912 | 2086 | 0.7544 [0.7461, 0.7626]; brut 31618.5/41912 | 0.3569 [0.3251, 0.3887]; brut 303/849 |
| branching:9..12 | Jass5k | 849 | 43998 | 41912 | 2086 | 0.7708 [0.7626, 0.7788]; brut 32304/41912 | 0.3781 [0.3451, 0.4111]; brut 321/849 |
| branching:9..12 | Jass50k | 849 | 43998 | 41912 | 2086 | 0.7971 [0.7892, 0.8047]; brut 33406/41912 | 0.4264 [0.3934, 0.4594]; brut 362/849 |
| branching:9..12 | Jass200k | 849 | 43998 | 41912 | 2086 | 0.8094 [0.8016, 0.8170]; brut 33922/41912 | 0.4841 [0.4499, 0.5183]; brut 411/849 |
| branching:9..12 | Scan1k | 849 | 43998 | 41912 | 2086 | 0.8467 [0.8402, 0.8530]; brut 35487/41912 | 0.5206 [0.4876, 0.5536]; brut 442/849 |
| branching:9..12 | Scan5k | 849 | 43998 | 41912 | 2086 | 0.8649 [0.8588, 0.8709]; brut 36249.5/41912 | 0.5300 [0.4959, 0.5630]; brut 450/849 |
| branching:9..12 | Scan50k | 849 | 43998 | 41912 | 2086 | 0.9045 [0.8995, 0.9093]; brut 37908/41912 | 0.6172 [0.5842, 0.6502]; brut 524/849 |
| branching:13..16 | T0 | 430 | 39562 | 36597 | 2965 | 0.5798 [0.5687, 0.5907]; brut 21217.5/36597 | 0.1535 [0.1209, 0.1884]; brut 66/430 |
| branching:13..16 | D1 | 430 | 39562 | 36597 | 2965 | 0.5974 [0.5859, 0.6088]; brut 21864/36597 | 0.1163 [0.0860, 0.1465]; brut 50/430 |
| branching:13..16 | RF1 | 430 | 39562 | 36597 | 2965 | 0.6360 [0.6241, 0.6476]; brut 23275/36597 | 0.1953 [0.1581, 0.2326]; brut 84/430 |
| branching:13..16 | T3-A | 430 | 39562 | 36597 | 2965 | 0.6372 [0.6256, 0.6485]; brut 23319/36597 | 0.1884 [0.1512, 0.2256]; brut 81/430 |
| branching:13..16 | Jass1k | 430 | 39562 | 36597 | 2965 | 0.7412 [0.7291, 0.7531]; brut 27126.5/36597 | 0.3837 [0.3372, 0.4302]; brut 165/430 |
| branching:13..16 | Jass5k | 430 | 39562 | 36597 | 2965 | 0.7626 [0.7514, 0.7736]; brut 27908/36597 | 0.4070 [0.3605, 0.4535]; brut 175/430 |
| branching:13..16 | Jass50k | 430 | 39562 | 36597 | 2965 | 0.7884 [0.7779, 0.7988]; brut 28853.5/36597 | 0.4488 [0.4023, 0.4953]; brut 193/430 |
| branching:13..16 | Jass200k | 430 | 39562 | 36597 | 2965 | 0.8007 [0.7904, 0.8108]; brut 29302/36597 | 0.4744 [0.4279, 0.5209]; brut 204/430 |
| branching:13..16 | Scan1k | 430 | 39562 | 36597 | 2965 | 0.8340 [0.8243, 0.8434]; brut 30521.5/36597 | 0.5047 [0.4581, 0.5512]; brut 217/430 |
| branching:13..16 | Scan5k | 430 | 39562 | 36597 | 2965 | 0.8593 [0.8502, 0.8681]; brut 31448.5/36597 | 0.5605 [0.5140, 0.6070]; brut 241/430 |
| branching:13..16 | Scan50k | 430 | 39562 | 36597 | 2965 | 0.8994 [0.8925, 0.9060]; brut 32914/36597 | 0.6465 [0.6000, 0.6907]; brut 278/430 |
| pieces:9..11 | T0 | 500 | 13028 | 10401 | 2627 | 0.5426 [0.5236, 0.5618]; brut 5643.5/10401 | 0.4140 [0.3700, 0.4580]; brut 207/500 |
| pieces:9..11 | D1 | 500 | 13028 | 10401 | 2627 | 0.5539 [0.5347, 0.5728]; brut 5761.5/10401 | 0.3460 [0.3040, 0.3880]; brut 173/500 |
| pieces:9..11 | RF1 | 500 | 13028 | 10401 | 2627 | 0.6389 [0.6184, 0.6596]; brut 6645.5/10401 | 0.5040 [0.4600, 0.5480]; brut 252/500 |
| pieces:9..11 | T3-A | 500 | 13028 | 10401 | 2627 | 0.6206 [0.6018, 0.6393]; brut 6454.5/10401 | 0.4740 [0.4300, 0.5180]; brut 237/500 |
| pieces:9..11 | Jass1k | 500 | 13028 | 10401 | 2627 | 0.7325 [0.7108, 0.7538]; brut 7619/10401 | 0.6140 [0.5720, 0.6560]; brut 307/500 |
| pieces:9..11 | Jass5k | 500 | 13028 | 10401 | 2627 | 0.7448 [0.7251, 0.7643]; brut 7747/10401 | 0.6000 [0.5560, 0.6420]; brut 300/500 |
| pieces:9..11 | Jass50k | 500 | 13028 | 10401 | 2627 | 0.7684 [0.7508, 0.7858]; brut 7992.5/10401 | 0.6460 [0.6040, 0.6880]; brut 323/500 |
| pieces:9..11 | Jass200k | 500 | 13028 | 10401 | 2627 | 0.7657 [0.7465, 0.7847]; brut 7964/10401 | 0.6600 [0.6180, 0.7020]; brut 330/500 |
| pieces:9..11 | Scan1k | 500 | 13028 | 10401 | 2627 | 0.7977 [0.7782, 0.8169]; brut 8296.5/10401 | 0.6880 [0.6480, 0.7280]; brut 344/500 |
| pieces:9..11 | Scan5k | 500 | 13028 | 10401 | 2627 | 0.8301 [0.8112, 0.8483]; brut 8633.5/10401 | 0.7280 [0.6880, 0.7660]; brut 364/500 |
| pieces:9..11 | Scan50k | 500 | 13028 | 10401 | 2627 | 0.8963 [0.8824, 0.9092]; brut 9322.5/10401 | 0.8180 [0.7840, 0.8520]; brut 409/500 |
| pieces:12..15 | T0 | 242 | 8142 | 6979 | 1163 | 0.5662 [0.5452, 0.5868]; brut 3951.5/6979 | 0.3058 [0.2479, 0.3636]; brut 74/242 |
| pieces:12..15 | D1 | 242 | 8142 | 6979 | 1163 | 0.5615 [0.5381, 0.5847]; brut 3919/6979 | 0.2645 [0.2107, 0.3223]; brut 64/242 |
| pieces:12..15 | RF1 | 242 | 8142 | 6979 | 1163 | 0.6328 [0.6074, 0.6584]; brut 4416/6979 | 0.3347 [0.2769, 0.3967]; brut 81/242 |
| pieces:12..15 | T3-A | 242 | 8142 | 6979 | 1163 | 0.6369 [0.6129, 0.6605]; brut 4445/6979 | 0.3719 [0.3099, 0.4339]; brut 90/242 |
| pieces:12..15 | Jass1k | 242 | 8142 | 6979 | 1163 | 0.7026 [0.6769, 0.7283]; brut 4903.5/6979 | 0.4793 [0.4174, 0.5413]; brut 116/242 |
| pieces:12..15 | Jass5k | 242 | 8142 | 6979 | 1163 | 0.7287 [0.7045, 0.7528]; brut 5085.5/6979 | 0.5000 [0.4380, 0.5620]; brut 121/242 |
| pieces:12..15 | Jass50k | 242 | 8142 | 6979 | 1163 | 0.7662 [0.7468, 0.7858]; brut 5347/6979 | 0.5785 [0.5165, 0.6405]; brut 140/242 |
| pieces:12..15 | Jass200k | 242 | 8142 | 6979 | 1163 | 0.7821 [0.7600, 0.8044]; brut 5458.5/6979 | 0.5868 [0.5248, 0.6488]; brut 142/242 |
| pieces:12..15 | Scan1k | 242 | 8142 | 6979 | 1163 | 0.7769 [0.7532, 0.8001]; brut 5422/6979 | 0.5537 [0.4917, 0.6157]; brut 134/242 |
| pieces:12..15 | Scan5k | 242 | 8142 | 6979 | 1163 | 0.8076 [0.7871, 0.8275]; brut 5636.5/6979 | 0.5992 [0.5372, 0.6612]; brut 145/242 |
| pieces:12..15 | Scan50k | 242 | 8142 | 6979 | 1163 | 0.8761 [0.8603, 0.8915]; brut 6114/6979 | 0.7521 [0.6983, 0.8058]; brut 182/242 |
| pieces:16..19 | T0 | 258 | 11720 | 11501 | 219 | 0.5399 [0.5231, 0.5565]; brut 6209.5/11501 | 0.1938 [0.1473, 0.2442]; brut 50/258 |
| pieces:16..19 | D1 | 258 | 11720 | 11501 | 219 | 0.5680 [0.5473, 0.5889]; brut 6533/11501 | 0.1783 [0.1318, 0.2248]; brut 46/258 |
| pieces:16..19 | RF1 | 258 | 11720 | 11501 | 219 | 0.6166 [0.5952, 0.6379]; brut 7092/11501 | 0.2481 [0.1977, 0.3023]; brut 64/258 |
| pieces:16..19 | T3-A | 258 | 11720 | 11501 | 219 | 0.6166 [0.5962, 0.6369]; brut 7092/11501 | 0.2674 [0.2132, 0.3217]; brut 69/258 |
| pieces:16..19 | Jass1k | 258 | 11720 | 11501 | 219 | 0.7137 [0.6939, 0.7331]; brut 8208.5/11501 | 0.3605 [0.3023, 0.4186]; brut 93/258 |
| pieces:16..19 | Jass5k | 258 | 11720 | 11501 | 219 | 0.7452 [0.7284, 0.7618]; brut 8571/11501 | 0.3876 [0.3295, 0.4457]; brut 100/258 |
| pieces:16..19 | Jass50k | 258 | 11720 | 11501 | 219 | 0.7718 [0.7534, 0.7899]; brut 8876.5/11501 | 0.4264 [0.3682, 0.4884]; brut 110/258 |
| pieces:16..19 | Jass200k | 258 | 11720 | 11501 | 219 | 0.7908 [0.7733, 0.8078]; brut 9095/11501 | 0.5194 [0.4574, 0.5814]; brut 134/258 |
| pieces:16..19 | Scan1k | 258 | 11720 | 11501 | 219 | 0.8071 [0.7930, 0.8208]; brut 9282/11501 | 0.4922 [0.4302, 0.5543]; brut 127/258 |
| pieces:16..19 | Scan5k | 258 | 11720 | 11501 | 219 | 0.8380 [0.8245, 0.8510]; brut 9637.5/11501 | 0.5504 [0.4884, 0.6124]; brut 142/258 |
| pieces:16..19 | Scan50k | 258 | 11720 | 11501 | 219 | 0.8794 [0.8676, 0.8910]; brut 10114.5/11501 | 0.6589 [0.6008, 0.7171]; brut 170/258 |
| pieces:20..24 | T0 | 274 | 16404 | 16086 | 318 | 0.5748 [0.5611, 0.5883]; brut 9245.5/16086 | 0.1752 [0.1314, 0.2226]; brut 48/274 |
| pieces:20..24 | D1 | 274 | 16404 | 16086 | 318 | 0.5980 [0.5831, 0.6127]; brut 9619/16086 | 0.0985 [0.0657, 0.1350]; brut 27/274 |
| pieces:20..24 | RF1 | 274 | 16404 | 16086 | 318 | 0.6330 [0.6168, 0.6487]; brut 10182/16086 | 0.1971 [0.1496, 0.2445]; brut 54/274 |
| pieces:20..24 | T3-A | 274 | 16404 | 16086 | 318 | 0.6416 [0.6265, 0.6563]; brut 10321/16086 | 0.2044 [0.1569, 0.2518]; brut 56/274 |
| pieces:20..24 | Jass1k | 274 | 16404 | 16086 | 318 | 0.7387 [0.7249, 0.7526]; brut 11883.5/16086 | 0.3321 [0.2774, 0.3869]; brut 91/274 |
| pieces:20..24 | Jass5k | 274 | 16404 | 16086 | 318 | 0.7487 [0.7336, 0.7638]; brut 12043.5/16086 | 0.3942 [0.3358, 0.4526]; brut 108/274 |
| pieces:20..24 | Jass50k | 274 | 16404 | 16086 | 318 | 0.7774 [0.7624, 0.7922]; brut 12506/16086 | 0.3905 [0.3321, 0.4489]; brut 107/274 |
| pieces:20..24 | Jass200k | 274 | 16404 | 16086 | 318 | 0.7911 [0.7770, 0.8051]; brut 12726/16086 | 0.4307 [0.3723, 0.4891]; brut 118/274 |
| pieces:20..24 | Scan1k | 274 | 16404 | 16086 | 318 | 0.8330 [0.8216, 0.8440]; brut 13399/16086 | 0.4489 [0.3905, 0.5073]; brut 123/274 |
| pieces:20..24 | Scan5k | 274 | 16404 | 16086 | 318 | 0.8506 [0.8393, 0.8613]; brut 13682/16086 | 0.4453 [0.3869, 0.5036]; brut 122/274 |
| pieces:20..24 | Scan50k | 274 | 16404 | 16086 | 318 | 0.8934 [0.8851, 0.9015]; brut 14371.5/16086 | 0.5803 [0.5219, 0.6387]; brut 159/274 |
| pieces:25..29 | T0 | 226 | 14611 | 14225 | 386 | 0.5706 [0.5530, 0.5881]; brut 8117/14225 | 0.1681 [0.1195, 0.2168]; brut 38/226 |
| pieces:25..29 | D1 | 226 | 14611 | 14225 | 386 | 0.6121 [0.5966, 0.6272]; brut 8707/14225 | 0.1726 [0.1239, 0.2212]; brut 39/226 |
| pieces:25..29 | RF1 | 226 | 14611 | 14225 | 386 | 0.6337 [0.6163, 0.6506]; brut 9015/14225 | 0.1858 [0.1372, 0.2389]; brut 42/226 |
| pieces:25..29 | T3-A | 226 | 14611 | 14225 | 386 | 0.6415 [0.6246, 0.6583]; brut 9126/14225 | 0.2035 [0.1504, 0.2566]; brut 46/226 |
| pieces:25..29 | Jass1k | 226 | 14611 | 14225 | 386 | 0.7378 [0.7208, 0.7544]; brut 10495.5/14225 | 0.3407 [0.2788, 0.4027]; brut 77/226 |
| pieces:25..29 | Jass5k | 226 | 14611 | 14225 | 386 | 0.7577 [0.7429, 0.7723]; brut 10778/14225 | 0.3540 [0.2920, 0.4159]; brut 80/226 |
| pieces:25..29 | Jass50k | 226 | 14611 | 14225 | 386 | 0.7859 [0.7716, 0.8000]; brut 11180/14225 | 0.4204 [0.3584, 0.4867]; brut 95/226 |
| pieces:25..29 | Jass200k | 226 | 14611 | 14225 | 386 | 0.7984 [0.7847, 0.8118]; brut 11357/14225 | 0.4735 [0.4071, 0.5398]; brut 107/226 |
| pieces:25..29 | Scan1k | 226 | 14611 | 14225 | 386 | 0.8518 [0.8407, 0.8625]; brut 12117.5/14225 | 0.5044 [0.4381, 0.5708]; brut 114/226 |
| pieces:25..29 | Scan5k | 226 | 14611 | 14225 | 386 | 0.8669 [0.8568, 0.8765]; brut 12331/14225 | 0.5398 [0.4735, 0.6062]; brut 122/226 |
| pieces:25..29 | Scan50k | 226 | 14611 | 14225 | 386 | 0.8987 [0.8894, 0.9076]; brut 12784/14225 | 0.5973 [0.5310, 0.6593]; brut 135/226 |
| pieces:30..34 | T0 | 318 | 18887 | 18298 | 589 | 0.6109 [0.5976, 0.6243]; brut 11179/18298 | 0.2170 [0.1730, 0.2642]; brut 69/318 |
| pieces:30..34 | D1 | 318 | 18887 | 18298 | 589 | 0.6175 [0.6028, 0.6317]; brut 11299/18298 | 0.1447 [0.1069, 0.1855]; brut 46/318 |
| pieces:30..34 | RF1 | 318 | 18887 | 18298 | 589 | 0.6578 [0.6436, 0.6717]; brut 12037/18298 | 0.2107 [0.1667, 0.2547]; brut 67/318 |
| pieces:30..34 | T3-A | 318 | 18887 | 18298 | 589 | 0.6621 [0.6486, 0.6754]; brut 12115/18298 | 0.2107 [0.1667, 0.2547]; brut 67/318 |
| pieces:30..34 | Jass1k | 318 | 18887 | 18298 | 589 | 0.7741 [0.7624, 0.7857]; brut 14164.5/18298 | 0.3899 [0.3365, 0.4434]; brut 124/318 |
| pieces:30..34 | Jass5k | 318 | 18887 | 18298 | 589 | 0.7942 [0.7822, 0.8057]; brut 14531.5/18298 | 0.4182 [0.3648, 0.4717]; brut 133/318 |
| pieces:30..34 | Jass50k | 318 | 18887 | 18298 | 589 | 0.8138 [0.8030, 0.8244]; brut 14891/18298 | 0.4654 [0.4119, 0.5189]; brut 148/318 |
| pieces:30..34 | Jass200k | 318 | 18887 | 18298 | 589 | 0.8284 [0.8182, 0.8383]; brut 15157.5/18298 | 0.5000 [0.4465, 0.5535]; brut 159/318 |
| pieces:30..34 | Scan1k | 318 | 18887 | 18298 | 589 | 0.8728 [0.8652, 0.8803]; brut 15971/18298 | 0.5849 [0.5314, 0.6384]; brut 186/318 |
| pieces:30..34 | Scan5k | 318 | 18887 | 18298 | 589 | 0.8936 [0.8862, 0.9007]; brut 16351/18298 | 0.6132 [0.5597, 0.6667]; brut 195/318 |
| pieces:30..34 | Scan50k | 318 | 18887 | 18298 | 589 | 0.9204 [0.9145, 0.9261]; brut 16841.5/18298 | 0.6321 [0.5786, 0.6855]; brut 201/318 |
| pieces:35..40 | T0 | 182 | 8643 | 8422 | 221 | 0.6447 [0.6273, 0.6619]; brut 5430/8422 | 0.2912 [0.2253, 0.3571]; brut 53/182 |
| pieces:35..40 | D1 | 182 | 8643 | 8422 | 221 | 0.6236 [0.6026, 0.6439]; brut 5252/8422 | 0.2143 [0.1538, 0.2747]; brut 39/182 |
| pieces:35..40 | RF1 | 182 | 8643 | 8422 | 221 | 0.7026 [0.6840, 0.7203]; brut 5917/8422 | 0.2967 [0.2308, 0.3626]; brut 54/182 |
| pieces:35..40 | T3-A | 182 | 8643 | 8422 | 221 | 0.6874 [0.6691, 0.7054]; brut 5789/8422 | 0.2912 [0.2253, 0.3571]; brut 53/182 |
| pieces:35..40 | Jass1k | 182 | 8643 | 8422 | 221 | 0.8233 [0.8077, 0.8380]; brut 6934/8422 | 0.4835 [0.4121, 0.5549]; brut 88/182 |
| pieces:35..40 | Jass5k | 182 | 8643 | 8422 | 221 | 0.8343 [0.8197, 0.8480]; brut 7026.5/8422 | 0.4341 [0.3626, 0.5055]; brut 79/182 |
| pieces:35..40 | Jass50k | 182 | 8643 | 8422 | 221 | 0.8513 [0.8370, 0.8650]; brut 7169.5/8422 | 0.5549 [0.4835, 0.6264]; brut 101/182 |
| pieces:35..40 | Jass200k | 182 | 8643 | 8422 | 221 | 0.8590 [0.8455, 0.8718]; brut 7234.5/8422 | 0.5495 [0.4780, 0.6209]; brut 100/182 |
| pieces:35..40 | Scan1k | 182 | 8643 | 8422 | 221 | 0.8944 [0.8846, 0.9039]; brut 7532.5/8422 | 0.6429 [0.5714, 0.7088]; brut 117/182 |
| pieces:35..40 | Scan5k | 182 | 8643 | 8422 | 221 | 0.9102 [0.9012, 0.9188]; brut 7665.5/8422 | 0.6868 [0.6209, 0.7527]; brut 125/182 |
| pieces:35..40 | Scan50k | 182 | 8643 | 8422 | 221 | 0.9412 [0.9336, 0.9483]; brut 7926.5/8422 | 0.7308 [0.6648, 0.7912]; brut 133/182 |

### DEEP512

| Strate | Signal | Parents | Pairs totaux | Pairs comparables | Ties référence | Pairwise | Top-hit |
|---|---|---:|---:|---:|---:|---:|---:|
| phase:P0 | T0 | 128 | 7258 | 7026 | 232 | 0.6176 [0.5965, 0.6386]; brut 4339.5/7026 | 0.2188 [0.1484, 0.2891]; brut 28/128 |
| phase:P0 | D1 | 128 | 7258 | 7026 | 232 | 0.6344 [0.6111, 0.6567]; brut 4457/7026 | 0.2500 [0.1797, 0.3281]; brut 32/128 |
| phase:P0 | RF1 | 128 | 7258 | 7026 | 232 | 0.6883 [0.6652, 0.7109]; brut 4836/7026 | 0.2422 [0.1719, 0.3203]; brut 31/128 |
| phase:P0 | T3-A | 128 | 7258 | 7026 | 232 | 0.6567 [0.6352, 0.6778]; brut 4614/7026 | 0.2344 [0.1641, 0.3125]; brut 30/128 |
| phase:P0 | Jass1k | 128 | 7258 | 7026 | 232 | 0.7804 [0.7576, 0.8017]; brut 5483/7026 | 0.4375 [0.3516, 0.5234]; brut 56/128 |
| phase:P0 | Jass5k | 128 | 7258 | 7026 | 232 | 0.8095 [0.7908, 0.8273]; brut 5687.5/7026 | 0.4609 [0.3750, 0.5469]; brut 59/128 |
| phase:P0 | Jass50k | 128 | 7258 | 7026 | 232 | 0.8237 [0.8052, 0.8414]; brut 5787/7026 | 0.5156 [0.4297, 0.6016]; brut 66/128 |
| phase:P0 | Jass200k | 128 | 7258 | 7026 | 232 | 0.8335 [0.8163, 0.8497]; brut 5856/7026 | 0.5703 [0.4844, 0.6562]; brut 73/128 |
| phase:P0 | Jass1M | 128 | 7258 | 7026 | 232 | 0.8375 [0.8190, 0.8548]; brut 5884.5/7026 | 0.4922 [0.4062, 0.5781]; brut 63/128 |
| phase:P0 | Scan1k | 128 | 7258 | 7026 | 232 | 0.8666 [0.8531, 0.8795]; brut 6089/7026 | 0.4844 [0.3984, 0.5703]; brut 62/128 |
| phase:P0 | Scan5k | 128 | 7258 | 7026 | 232 | 0.8815 [0.8663, 0.8957]; brut 6193.5/7026 | 0.5859 [0.5000, 0.6719]; brut 75/128 |
| phase:P0 | Scan50k | 128 | 7258 | 7026 | 232 | 0.9085 [0.8980, 0.9183]; brut 6383/7026 | 0.6719 [0.5859, 0.7500]; brut 86/128 |
| phase:P0 | Scan200k | 128 | 7258 | 7026 | 232 | 0.9206 [0.9100, 0.9307]; brut 6468/7026 | 0.6953 [0.6172, 0.7734]; brut 89/128 |
| phase:P0 | Scan1M | 128 | 7258 | 7026 | 232 | 0.9437 [0.9348, 0.9518]; brut 6630.5/7026 | 0.6797 [0.6016, 0.7578]; brut 87/128 |
| phase:P1 | T0 | 128 | 8117 | 7953 | 164 | 0.5673 [0.5439, 0.5907]; brut 4512/7953 | 0.2031 [0.1328, 0.2734]; brut 26/128 |
| phase:P1 | D1 | 128 | 8117 | 7953 | 164 | 0.6146 [0.5915, 0.6363]; brut 4888/7953 | 0.1719 [0.1094, 0.2422]; brut 22/128 |
| phase:P1 | RF1 | 128 | 8117 | 7953 | 164 | 0.6458 [0.6215, 0.6688]; brut 5136/7953 | 0.2266 [0.1562, 0.3047]; brut 29/128 |
| phase:P1 | T3-A | 128 | 8117 | 7953 | 164 | 0.6351 [0.6111, 0.6585]; brut 5051/7953 | 0.2109 [0.1406, 0.2812]; brut 27/128 |
| phase:P1 | Jass1k | 128 | 8117 | 7953 | 164 | 0.7297 [0.7069, 0.7518]; brut 5803/7953 | 0.3281 [0.2500, 0.4141]; brut 42/128 |
| phase:P1 | Jass5k | 128 | 8117 | 7953 | 164 | 0.7591 [0.7395, 0.7786]; brut 6037/7953 | 0.3516 [0.2734, 0.4375]; brut 45/128 |
| phase:P1 | Jass50k | 128 | 8117 | 7953 | 164 | 0.7833 [0.7629, 0.8026]; brut 6229.5/7953 | 0.3906 [0.3047, 0.4766]; brut 50/128 |
| phase:P1 | Jass200k | 128 | 8117 | 7953 | 164 | 0.7991 [0.7801, 0.8178]; brut 6355.5/7953 | 0.4375 [0.3516, 0.5234]; brut 56/128 |
| phase:P1 | Jass1M | 128 | 8117 | 7953 | 164 | 0.8144 [0.7953, 0.8331]; brut 6477/7953 | 0.4219 [0.3359, 0.5078]; brut 54/128 |
| phase:P1 | Scan1k | 128 | 8117 | 7953 | 164 | 0.8355 [0.8175, 0.8529]; brut 6645/7953 | 0.4219 [0.3359, 0.5078]; brut 54/128 |
| phase:P1 | Scan5k | 128 | 8117 | 7953 | 164 | 0.8428 [0.8248, 0.8593]; brut 6703/7953 | 0.4297 [0.3438, 0.5156]; brut 55/128 |
| phase:P1 | Scan50k | 128 | 8117 | 7953 | 164 | 0.8775 [0.8641, 0.8900]; brut 6978.5/7953 | 0.5078 [0.4219, 0.5938]; brut 65/128 |
| phase:P1 | Scan200k | 128 | 8117 | 7953 | 164 | 0.8959 [0.8833, 0.9077]; brut 7125/7953 | 0.6484 [0.5625, 0.7266]; brut 83/128 |
| phase:P1 | Scan1M | 128 | 8117 | 7953 | 164 | 0.9268 [0.9186, 0.9348]; brut 7371/7953 | 0.6016 [0.5156, 0.6875]; brut 77/128 |
| phase:P2 | T0 | 128 | 5008 | 4656 | 352 | 0.5577 [0.5316, 0.5827]; brut 2596.5/4656 | 0.3594 [0.2734, 0.4453]; brut 46/128 |
| phase:P2 | D1 | 128 | 5008 | 4656 | 352 | 0.5588 [0.5299, 0.5877]; brut 2602/4656 | 0.2500 [0.1797, 0.3281]; brut 32/128 |
| phase:P2 | RF1 | 128 | 5008 | 4656 | 352 | 0.6113 [0.5739, 0.6487]; brut 2846/4656 | 0.3125 [0.2344, 0.3906]; brut 40/128 |
| phase:P2 | T3-A | 128 | 5008 | 4656 | 352 | 0.6390 [0.6065, 0.6701]; brut 2975/4656 | 0.3750 [0.2891, 0.4609]; brut 48/128 |
| phase:P2 | Jass1k | 128 | 5008 | 4656 | 352 | 0.6983 [0.6694, 0.7282]; brut 3251.5/4656 | 0.4453 [0.3594, 0.5312]; brut 57/128 |
| phase:P2 | Jass5k | 128 | 5008 | 4656 | 352 | 0.7316 [0.7043, 0.7579]; brut 3406.5/4656 | 0.4844 [0.3984, 0.5703]; brut 62/128 |
| phase:P2 | Jass50k | 128 | 5008 | 4656 | 352 | 0.7477 [0.7163, 0.7773]; brut 3481.5/4656 | 0.5312 [0.4453, 0.6172]; brut 68/128 |
| phase:P2 | Jass200k | 128 | 5008 | 4656 | 352 | 0.7744 [0.7479, 0.7999]; brut 3605.5/4656 | 0.5000 [0.4141, 0.5859]; brut 64/128 |
| phase:P2 | Jass1M | 128 | 5008 | 4656 | 352 | 0.7868 [0.7592, 0.8134]; brut 3663.5/4656 | 0.5391 [0.4531, 0.6250]; brut 69/128 |
| phase:P2 | Scan1k | 128 | 5008 | 4656 | 352 | 0.7806 [0.7574, 0.8036]; brut 3634.5/4656 | 0.5234 [0.4375, 0.6094]; brut 67/128 |
| phase:P2 | Scan5k | 128 | 5008 | 4656 | 352 | 0.8041 [0.7821, 0.8253]; brut 3744/4656 | 0.5703 [0.4844, 0.6562]; brut 73/128 |
| phase:P2 | Scan50k | 128 | 5008 | 4656 | 352 | 0.8424 [0.8218, 0.8626]; brut 3922/4656 | 0.6875 [0.6094, 0.7656]; brut 88/128 |
| phase:P2 | Scan200k | 128 | 5008 | 4656 | 352 | 0.8664 [0.8453, 0.8870]; brut 4034/4656 | 0.7266 [0.6484, 0.8047]; brut 93/128 |
| phase:P2 | Scan1M | 128 | 5008 | 4656 | 352 | 0.9274 [0.9142, 0.9402]; brut 4318/4656 | 0.8516 [0.7891, 0.9062]; brut 109/128 |
| phase:P3 | T0 | 128 | 3799 | 2665 | 1134 | 0.5437 [0.5057, 0.5808]; brut 1449/2665 | 0.4922 [0.4062, 0.5781]; brut 63/128 |
| phase:P3 | D1 | 128 | 3799 | 2665 | 1134 | 0.5368 [0.4948, 0.5771]; brut 1430.5/2665 | 0.3828 [0.2969, 0.4688]; brut 49/128 |
| phase:P3 | RF1 | 128 | 3799 | 2665 | 1134 | 0.6381 [0.5970, 0.6788]; brut 1700.5/2665 | 0.4922 [0.4062, 0.5781]; brut 63/128 |
| phase:P3 | T3-A | 128 | 3799 | 2665 | 1134 | 0.5908 [0.5472, 0.6327]; brut 1574.5/2665 | 0.5000 [0.4141, 0.5859]; brut 64/128 |
| phase:P3 | Jass1k | 128 | 3799 | 2665 | 1134 | 0.7454 [0.7038, 0.7838]; brut 1986.5/2665 | 0.6562 [0.5703, 0.7344]; brut 84/128 |
| phase:P3 | Jass5k | 128 | 3799 | 2665 | 1134 | 0.7516 [0.7088, 0.7900]; brut 2003/2665 | 0.6250 [0.5391, 0.7109]; brut 80/128 |
| phase:P3 | Jass50k | 128 | 3799 | 2665 | 1134 | 0.7640 [0.7208, 0.8043]; brut 2036/2665 | 0.6797 [0.6016, 0.7578]; brut 87/128 |
| phase:P3 | Jass200k | 128 | 3799 | 2665 | 1134 | 0.7480 [0.7037, 0.7910]; brut 1993.5/2665 | 0.6406 [0.5547, 0.7266]; brut 82/128 |
| phase:P3 | Jass1M | 128 | 3799 | 2665 | 1134 | 0.7576 [0.7136, 0.7988]; brut 2019/2665 | 0.6094 [0.5234, 0.6953]; brut 78/128 |
| phase:P3 | Scan1k | 128 | 3799 | 2665 | 1134 | 0.8041 [0.7627, 0.8421]; brut 2143/2665 | 0.7500 [0.6719, 0.8203]; brut 96/128 |
| phase:P3 | Scan5k | 128 | 3799 | 2665 | 1134 | 0.8317 [0.7922, 0.8673]; brut 2216.5/2665 | 0.7891 [0.7188, 0.8594]; brut 101/128 |
| phase:P3 | Scan50k | 128 | 3799 | 2665 | 1134 | 0.8576 [0.8237, 0.8896]; brut 2285.5/2665 | 0.8281 [0.7578, 0.8906]; brut 106/128 |
| phase:P3 | Scan200k | 128 | 3799 | 2665 | 1134 | 0.8992 [0.8720, 0.9250]; brut 2396.5/2665 | 0.8594 [0.7969, 0.9141]; brut 110/128 |
| phase:P3 | Scan1M | 128 | 3799 | 2665 | 1134 | 0.9323 [0.9088, 0.9534]; brut 2484.5/2665 | 0.9062 [0.8516, 0.9531]; brut 116/128 |
| colour:white | T0 | 264 | 12444 | 11620 | 824 | 0.5790 [0.5598, 0.5978]; brut 6728.5/11620 | 0.2955 [0.2424, 0.3523]; brut 78/264 |
| colour:white | D1 | 264 | 12444 | 11620 | 824 | 0.5948 [0.5746, 0.6142]; brut 6911.5/11620 | 0.2197 [0.1705, 0.2689]; brut 58/264 |
| colour:white | RF1 | 264 | 12444 | 11620 | 824 | 0.6469 [0.6252, 0.6677]; brut 7516.5/11620 | 0.2727 [0.2197, 0.3258]; brut 72/264 |
| colour:white | T3-A | 264 | 12444 | 11620 | 824 | 0.6355 [0.6157, 0.6546]; brut 7384.5/11620 | 0.3068 [0.2538, 0.3636]; brut 81/264 |
| colour:white | Jass1k | 264 | 12444 | 11620 | 824 | 0.7371 [0.7167, 0.7572]; brut 8565.5/11620 | 0.4280 [0.3674, 0.4886]; brut 113/264 |
| colour:white | Jass5k | 264 | 12444 | 11620 | 824 | 0.7711 [0.7537, 0.7880]; brut 8960.5/11620 | 0.4659 [0.4053, 0.5265]; brut 123/264 |
| colour:white | Jass50k | 264 | 12444 | 11620 | 824 | 0.7847 [0.7668, 0.8019]; brut 9118.5/11620 | 0.5303 [0.4697, 0.5909]; brut 140/264 |
| colour:white | Jass200k | 264 | 12444 | 11620 | 824 | 0.8015 [0.7848, 0.8177]; brut 9313.5/11620 | 0.5379 [0.4773, 0.5985]; brut 142/264 |
| colour:white | Jass1M | 264 | 12444 | 11620 | 824 | 0.8102 [0.7928, 0.8269]; brut 9414/11620 | 0.5227 [0.4621, 0.5833]; brut 138/264 |
| colour:white | Scan1k | 264 | 12444 | 11620 | 824 | 0.8319 [0.8174, 0.8460]; brut 9667/11620 | 0.5000 [0.4394, 0.5606]; brut 132/264 |
| colour:white | Scan5k | 264 | 12444 | 11620 | 824 | 0.8466 [0.8335, 0.8592]; brut 9837/11620 | 0.5530 [0.4924, 0.6136]; brut 146/264 |
| colour:white | Scan50k | 264 | 12444 | 11620 | 824 | 0.8778 [0.8661, 0.8891]; brut 10200.5/11620 | 0.6705 [0.6136, 0.7273]; brut 177/264 |
| colour:white | Scan200k | 264 | 12444 | 11620 | 824 | 0.8976 [0.8860, 0.9085]; brut 10430/11620 | 0.7159 [0.6591, 0.7689]; brut 189/264 |
| colour:white | Scan1M | 264 | 12444 | 11620 | 824 | 0.9290 [0.9199, 0.9376]; brut 10795.5/11620 | 0.7803 [0.7311, 0.8295]; brut 206/264 |
| colour:black | T0 | 248 | 11738 | 10680 | 1058 | 0.5776 [0.5600, 0.5953]; brut 6168.5/10680 | 0.3427 [0.2863, 0.4032]; brut 85/248 |
| colour:black | D1 | 248 | 11738 | 10680 | 1058 | 0.6054 [0.5855, 0.6247]; brut 6466/10680 | 0.3105 [0.2540, 0.3669]; brut 77/248 |
| colour:black | RF1 | 248 | 11738 | 10680 | 1058 | 0.6556 [0.6344, 0.6760]; brut 7002/10680 | 0.3669 [0.3065, 0.4274]; brut 91/248 |
| colour:black | T3-A | 248 | 11738 | 10680 | 1058 | 0.6395 [0.6196, 0.6589]; brut 6830/10680 | 0.3548 [0.2944, 0.4153]; brut 88/248 |
| colour:black | Jass1k | 248 | 11738 | 10680 | 1058 | 0.7452 [0.7268, 0.7632]; brut 7958.5/10680 | 0.5081 [0.4476, 0.5685]; brut 126/248 |
| colour:black | Jass5k | 248 | 11738 | 10680 | 1058 | 0.7653 [0.7481, 0.7823]; brut 8173.5/10680 | 0.4960 [0.4355, 0.5565]; brut 123/248 |
| colour:black | Jass50k | 248 | 11738 | 10680 | 1058 | 0.7880 [0.7693, 0.8057]; brut 8415.5/10680 | 0.5282 [0.4677, 0.5887]; brut 131/248 |
| colour:black | Jass200k | 248 | 11738 | 10680 | 1058 | 0.7956 [0.7784, 0.8123]; brut 8497/10680 | 0.5363 [0.4758, 0.5968]; brut 133/248 |
| colour:black | Jass1M | 248 | 11738 | 10680 | 1058 | 0.8081 [0.7911, 0.8244]; brut 8630/10680 | 0.5081 [0.4476, 0.5685]; brut 126/248 |
| colour:black | Scan1k | 248 | 11738 | 10680 | 1058 | 0.8281 [0.8119, 0.8438]; brut 8844.5/10680 | 0.5927 [0.5323, 0.6532]; brut 147/248 |
| colour:black | Scan5k | 248 | 11738 | 10680 | 1058 | 0.8446 [0.8273, 0.8607]; brut 9020/10680 | 0.6371 [0.5766, 0.6976]; brut 158/248 |
| colour:black | Scan50k | 248 | 11738 | 10680 | 1058 | 0.8772 [0.8641, 0.8898]; brut 9368.5/10680 | 0.6774 [0.6169, 0.7339]; brut 168/248 |
| colour:black | Scan200k | 248 | 11738 | 10680 | 1058 | 0.8983 [0.8867, 0.9094]; brut 9593.5/10680 | 0.7500 [0.6935, 0.8024]; brut 186/248 |
| colour:black | Scan1M | 248 | 11738 | 10680 | 1058 | 0.9371 [0.9306, 0.9436]; brut 10008.5/10680 | 0.7379 [0.6815, 0.7903]; brut 183/248 |
| branching:2..4 | T0 | 97 | 217 | 139 | 78 | 0.5863 [0.4924, 0.6756]; brut 81.5/139 | 0.7113 [0.6186, 0.8041]; brut 69/97 |
| branching:2..4 | D1 | 97 | 217 | 139 | 78 | 0.5504 [0.4552, 0.6468]; brut 76.5/139 | 0.7113 [0.6186, 0.8041]; brut 69/97 |
| branching:2..4 | RF1 | 97 | 217 | 139 | 78 | 0.6295 [0.5267, 0.7263]; brut 87.5/139 | 0.7320 [0.6392, 0.8144]; brut 71/97 |
| branching:2..4 | T3-A | 97 | 217 | 139 | 78 | 0.6583 [0.5591, 0.7457]; brut 91.5/139 | 0.7423 [0.6495, 0.8247]; brut 72/97 |
| branching:2..4 | Jass1k | 97 | 217 | 139 | 78 | 0.8022 [0.7280, 0.8741]; brut 111.5/139 | 0.8557 [0.7835, 0.9175]; brut 83/97 |
| branching:2..4 | Jass5k | 97 | 217 | 139 | 78 | 0.7626 [0.6866, 0.8370]; brut 106/139 | 0.8351 [0.7629, 0.9072]; brut 81/97 |
| branching:2..4 | Jass50k | 97 | 217 | 139 | 78 | 0.8129 [0.7377, 0.8870]; brut 113/139 | 0.8763 [0.8041, 0.9381]; brut 85/97 |
| branching:2..4 | Jass200k | 97 | 217 | 139 | 78 | 0.8309 [0.7628, 0.8984]; brut 115.5/139 | 0.8763 [0.8041, 0.9381]; brut 85/97 |
| branching:2..4 | Jass1M | 97 | 217 | 139 | 78 | 0.8165 [0.7500, 0.8818]; brut 113.5/139 | 0.8454 [0.7732, 0.9175]; brut 82/97 |
| branching:2..4 | Scan1k | 97 | 217 | 139 | 78 | 0.8489 [0.7812, 0.9113]; brut 118/139 | 0.9175 [0.8557, 0.9691]; brut 89/97 |
| branching:2..4 | Scan5k | 97 | 217 | 139 | 78 | 0.8993 [0.8490, 0.9462]; brut 125/139 | 0.9381 [0.8866, 0.9794]; brut 91/97 |
| branching:2..4 | Scan50k | 97 | 217 | 139 | 78 | 0.9281 [0.8707, 0.9729]; brut 129/139 | 0.9485 [0.8969, 0.9897]; brut 92/97 |
| branching:2..4 | Scan200k | 97 | 217 | 139 | 78 | 0.9676 [0.9343, 0.9928]; brut 134.5/139 | 0.9691 [0.9278, 1.0000]; brut 94/97 |
| branching:2..4 | Scan1M | 97 | 217 | 139 | 78 | 0.9784 [0.9533, 1.0000]; brut 136/139 | 0.9794 [0.9485, 1.0000]; brut 95/97 |
| branching:5..8 | T0 | 87 | 1682 | 1580 | 102 | 0.5092 [0.4738, 0.5437]; brut 804.5/1580 | 0.2759 [0.1839, 0.3678]; brut 24/87 |
| branching:5..8 | D1 | 87 | 1682 | 1580 | 102 | 0.5899 [0.5488, 0.6301]; brut 932/1580 | 0.2069 [0.1264, 0.2989]; brut 18/87 |
| branching:5..8 | RF1 | 87 | 1682 | 1580 | 102 | 0.6994 [0.6636, 0.7341]; brut 1105/1580 | 0.2874 [0.1954, 0.3793]; brut 25/87 |
| branching:5..8 | T3-A | 87 | 1682 | 1580 | 102 | 0.6430 [0.6025, 0.6831]; brut 1016/1580 | 0.3333 [0.2414, 0.4368]; brut 29/87 |
| branching:5..8 | Jass1k | 87 | 1682 | 1580 | 102 | 0.7244 [0.6872, 0.7595]; brut 1144.5/1580 | 0.3448 [0.2414, 0.4483]; brut 30/87 |
| branching:5..8 | Jass5k | 87 | 1682 | 1580 | 102 | 0.7307 [0.6966, 0.7631]; brut 1154.5/1580 | 0.3333 [0.2414, 0.4368]; brut 29/87 |
| branching:5..8 | Jass50k | 87 | 1682 | 1580 | 102 | 0.7462 [0.7110, 0.7786]; brut 1179/1580 | 0.4023 [0.2989, 0.5057]; brut 35/87 |
| branching:5..8 | Jass200k | 87 | 1682 | 1580 | 102 | 0.7462 [0.7101, 0.7801]; brut 1179/1580 | 0.3678 [0.2644, 0.4713]; brut 32/87 |
| branching:5..8 | Jass1M | 87 | 1682 | 1580 | 102 | 0.7522 [0.7127, 0.7890]; brut 1188.5/1580 | 0.4023 [0.2989, 0.5057]; brut 35/87 |
| branching:5..8 | Scan1k | 87 | 1682 | 1580 | 102 | 0.7823 [0.7468, 0.8145]; brut 1236/1580 | 0.4713 [0.3678, 0.5747]; brut 41/87 |
| branching:5..8 | Scan5k | 87 | 1682 | 1580 | 102 | 0.8301 [0.8059, 0.8530]; brut 1311.5/1580 | 0.5977 [0.4943, 0.7011]; brut 52/87 |
| branching:5..8 | Scan50k | 87 | 1682 | 1580 | 102 | 0.8693 [0.8455, 0.8913]; brut 1373.5/1580 | 0.7011 [0.5977, 0.7931]; brut 61/87 |
| branching:5..8 | Scan200k | 87 | 1682 | 1580 | 102 | 0.9013 [0.8828, 0.9182]; brut 1424/1580 | 0.7701 [0.6782, 0.8506]; brut 67/87 |
| branching:5..8 | Scan1M | 87 | 1682 | 1580 | 102 | 0.9370 [0.9211, 0.9524]; brut 1480.5/1580 | 0.8046 [0.7241, 0.8851]; brut 70/87 |
| branching:9..12 | T0 | 203 | 10644 | 10079 | 565 | 0.5900 [0.5726, 0.6071]; brut 5947/10079 | 0.2315 [0.1724, 0.2906]; brut 47/203 |
| branching:9..12 | D1 | 203 | 10644 | 10079 | 565 | 0.5996 [0.5797, 0.6191]; brut 6043/10079 | 0.1576 [0.1084, 0.2069]; brut 32/203 |
| branching:9..12 | RF1 | 203 | 10644 | 10079 | 565 | 0.6429 [0.6220, 0.6636]; brut 6480/10079 | 0.1626 [0.1133, 0.2167]; brut 33/203 |
| branching:9..12 | T3-A | 203 | 10644 | 10079 | 565 | 0.6490 [0.6301, 0.6674]; brut 6541/10079 | 0.2365 [0.1773, 0.2956]; brut 48/203 |
| branching:9..12 | Jass1k | 203 | 10644 | 10079 | 565 | 0.7442 [0.7254, 0.7624]; brut 7501/10079 | 0.3695 [0.3054, 0.4384]; brut 75/203 |
| branching:9..12 | Jass5k | 203 | 10644 | 10079 | 565 | 0.7764 [0.7601, 0.7922]; brut 7825/10079 | 0.4039 [0.3350, 0.4729]; brut 82/203 |
| branching:9..12 | Jass50k | 203 | 10644 | 10079 | 565 | 0.7993 [0.7841, 0.8142]; brut 8056.5/10079 | 0.4581 [0.3892, 0.5271]; brut 93/203 |
| branching:9..12 | Jass200k | 203 | 10644 | 10079 | 565 | 0.8086 [0.7929, 0.8238]; brut 8150/10079 | 0.4581 [0.3892, 0.5271]; brut 93/203 |
| branching:9..12 | Jass1M | 203 | 10644 | 10079 | 565 | 0.8215 [0.8058, 0.8366]; brut 8279.5/10079 | 0.4236 [0.3547, 0.4926]; brut 86/203 |
| branching:9..12 | Scan1k | 203 | 10644 | 10079 | 565 | 0.8378 [0.8239, 0.8513]; brut 8444.5/10079 | 0.4335 [0.3645, 0.5025]; brut 88/203 |
| branching:9..12 | Scan5k | 203 | 10644 | 10079 | 565 | 0.8444 [0.8304, 0.8580]; brut 8511/10079 | 0.4483 [0.3793, 0.5172]; brut 91/203 |
| branching:9..12 | Scan50k | 203 | 10644 | 10079 | 565 | 0.8769 [0.8646, 0.8886]; brut 8838/10079 | 0.5911 [0.5222, 0.6601]; brut 120/203 |
| branching:9..12 | Scan200k | 203 | 10644 | 10079 | 565 | 0.8944 [0.8831, 0.9052]; brut 9015/10079 | 0.6108 [0.5419, 0.6749]; brut 124/203 |
| branching:9..12 | Scan1M | 203 | 10644 | 10079 | 565 | 0.9317 [0.9238, 0.9393]; brut 9391/10079 | 0.6995 [0.6355, 0.7635]; brut 142/203 |
| branching:13..16 | T0 | 125 | 11639 | 10502 | 1137 | 0.5774 [0.5559, 0.5986]; brut 6064/10502 | 0.1840 [0.1200, 0.2560]; brut 23/125 |
| branching:13..16 | D1 | 125 | 11639 | 10502 | 1137 | 0.6024 [0.5800, 0.6237]; brut 6326/10502 | 0.1280 [0.0720, 0.1920]; brut 16/125 |
| branching:13..16 | RF1 | 125 | 11639 | 10502 | 1137 | 0.6519 [0.6275, 0.6751]; brut 6846/10502 | 0.2720 [0.2000, 0.3520]; brut 34/125 |
| branching:13..16 | T3-A | 125 | 11639 | 10502 | 1137 | 0.6252 [0.6024, 0.6469]; brut 6566/10502 | 0.1600 [0.0960, 0.2240]; brut 20/125 |
| branching:13..16 | Jass1k | 125 | 11639 | 10502 | 1137 | 0.7396 [0.7170, 0.7617]; brut 7767/10502 | 0.4080 [0.3200, 0.4960]; brut 51/125 |
| branching:13..16 | Jass5k | 125 | 11639 | 10502 | 1137 | 0.7664 [0.7460, 0.7861]; brut 8048.5/10502 | 0.4320 [0.3440, 0.5200]; brut 54/125 |
| branching:13..16 | Jass50k | 125 | 11639 | 10502 | 1137 | 0.7794 [0.7570, 0.8007]; brut 8185.5/10502 | 0.4640 [0.3760, 0.5520]; brut 58/125 |
| branching:13..16 | Jass200k | 125 | 11639 | 10502 | 1137 | 0.7966 [0.7770, 0.8156]; brut 8366/10502 | 0.5200 [0.4320, 0.6080]; brut 65/125 |
| branching:13..16 | Jass1M | 125 | 11639 | 10502 | 1137 | 0.8058 [0.7858, 0.8250]; brut 8462.5/10502 | 0.4880 [0.4000, 0.5760]; brut 61/125 |
| branching:13..16 | Scan1k | 125 | 11639 | 10502 | 1137 | 0.8297 [0.8118, 0.8470]; brut 8713/10502 | 0.4880 [0.4000, 0.5760]; brut 61/125 |
| branching:13..16 | Scan5k | 125 | 11639 | 10502 | 1137 | 0.8484 [0.8304, 0.8652]; brut 8909.5/10502 | 0.5600 [0.4720, 0.6480]; brut 70/125 |
| branching:13..16 | Scan50k | 125 | 11639 | 10502 | 1137 | 0.8787 [0.8647, 0.8920]; brut 9228.5/10502 | 0.5760 [0.4880, 0.6640]; brut 72/125 |
| branching:13..16 | Scan200k | 125 | 11639 | 10502 | 1137 | 0.8998 [0.8865, 0.9125]; brut 9450/10502 | 0.7200 [0.6400, 0.8000]; brut 90/125 |
| branching:13..16 | Scan1M | 125 | 11639 | 10502 | 1137 | 0.9328 [0.9236, 0.9414]; brut 9796.5/10502 | 0.6560 [0.5680, 0.7360]; brut 82/125 |
| pieces:9..11 | T0 | 128 | 3799 | 2665 | 1134 | 0.5437 [0.5059, 0.5807]; brut 1449/2665 | 0.4922 [0.4062, 0.5781]; brut 63/128 |
| pieces:9..11 | D1 | 128 | 3799 | 2665 | 1134 | 0.5368 [0.4951, 0.5770]; brut 1430.5/2665 | 0.3828 [0.2969, 0.4688]; brut 49/128 |
| pieces:9..11 | RF1 | 128 | 3799 | 2665 | 1134 | 0.6381 [0.5971, 0.6786]; brut 1700.5/2665 | 0.4922 [0.4062, 0.5781]; brut 63/128 |
| pieces:9..11 | T3-A | 128 | 3799 | 2665 | 1134 | 0.5908 [0.5473, 0.6326]; brut 1574.5/2665 | 0.5000 [0.4141, 0.5859]; brut 64/128 |
| pieces:9..11 | Jass1k | 128 | 3799 | 2665 | 1134 | 0.7454 [0.7037, 0.7841]; brut 1986.5/2665 | 0.6562 [0.5703, 0.7344]; brut 84/128 |
| pieces:9..11 | Jass5k | 128 | 3799 | 2665 | 1134 | 0.7516 [0.7089, 0.7903]; brut 2003/2665 | 0.6250 [0.5391, 0.7109]; brut 80/128 |
| pieces:9..11 | Jass50k | 128 | 3799 | 2665 | 1134 | 0.7640 [0.7209, 0.8045]; brut 2036/2665 | 0.6797 [0.5938, 0.7578]; brut 87/128 |
| pieces:9..11 | Jass200k | 128 | 3799 | 2665 | 1134 | 0.7480 [0.7039, 0.7912]; brut 1993.5/2665 | 0.6406 [0.5547, 0.7188]; brut 82/128 |
| pieces:9..11 | Jass1M | 128 | 3799 | 2665 | 1134 | 0.7576 [0.7140, 0.7988]; brut 2019/2665 | 0.6094 [0.5234, 0.6953]; brut 78/128 |
| pieces:9..11 | Scan1k | 128 | 3799 | 2665 | 1134 | 0.8041 [0.7626, 0.8422]; brut 2143/2665 | 0.7500 [0.6719, 0.8203]; brut 96/128 |
| pieces:9..11 | Scan5k | 128 | 3799 | 2665 | 1134 | 0.8317 [0.7918, 0.8676]; brut 2216.5/2665 | 0.7891 [0.7188, 0.8594]; brut 101/128 |
| pieces:9..11 | Scan50k | 128 | 3799 | 2665 | 1134 | 0.8576 [0.8239, 0.8897]; brut 2285.5/2665 | 0.8281 [0.7578, 0.8906]; brut 106/128 |
| pieces:9..11 | Scan200k | 128 | 3799 | 2665 | 1134 | 0.8992 [0.8719, 0.9251]; brut 2396.5/2665 | 0.8594 [0.7969, 0.9141]; brut 110/128 |
| pieces:9..11 | Scan1M | 128 | 3799 | 2665 | 1134 | 0.9323 [0.9088, 0.9534]; brut 2484.5/2665 | 0.9062 [0.8516, 0.9531]; brut 116/128 |
| pieces:12..15 | T0 | 65 | 1985 | 1694 | 291 | 0.5788 [0.5362, 0.6179]; brut 980.5/1694 | 0.4154 [0.2923, 0.5385]; brut 27/65 |
| pieces:12..15 | D1 | 65 | 1985 | 1694 | 291 | 0.5401 [0.4965, 0.5855]; brut 915/1694 | 0.3077 [0.2000, 0.4154]; brut 20/65 |
| pieces:12..15 | RF1 | 65 | 1985 | 1694 | 291 | 0.6116 [0.5634, 0.6612]; brut 1036/1694 | 0.3538 [0.2462, 0.4769]; brut 23/65 |
| pieces:12..15 | T3-A | 65 | 1985 | 1694 | 291 | 0.6741 [0.6338, 0.7134]; brut 1142/1694 | 0.4462 [0.3231, 0.5692]; brut 29/65 |
| pieces:12..15 | Jass1k | 65 | 1985 | 1694 | 291 | 0.7102 [0.6693, 0.7489]; brut 1203/1694 | 0.4462 [0.3231, 0.5692]; brut 29/65 |
| pieces:12..15 | Jass5k | 65 | 1985 | 1694 | 291 | 0.7456 [0.7108, 0.7802]; brut 1263/1694 | 0.5385 [0.4154, 0.6615]; brut 35/65 |
| pieces:12..15 | Jass50k | 65 | 1985 | 1694 | 291 | 0.7645 [0.7304, 0.7968]; brut 1295/1694 | 0.6462 [0.5231, 0.7538]; brut 42/65 |
| pieces:12..15 | Jass200k | 65 | 1985 | 1694 | 291 | 0.7816 [0.7421, 0.8186]; brut 1324/1694 | 0.5385 [0.4154, 0.6615]; brut 35/65 |
| pieces:12..15 | Jass1M | 65 | 1985 | 1694 | 291 | 0.7848 [0.7425, 0.8248]; brut 1329.5/1694 | 0.6000 [0.4769, 0.7231]; brut 39/65 |
| pieces:12..15 | Scan1k | 65 | 1985 | 1694 | 291 | 0.7783 [0.7391, 0.8137]; brut 1318.5/1694 | 0.5692 [0.4462, 0.6923]; brut 37/65 |
| pieces:12..15 | Scan5k | 65 | 1985 | 1694 | 291 | 0.7984 [0.7594, 0.8334]; brut 1352.5/1694 | 0.6462 [0.5231, 0.7538]; brut 42/65 |
| pieces:12..15 | Scan50k | 65 | 1985 | 1694 | 291 | 0.8592 [0.8261, 0.8901]; brut 1455.5/1694 | 0.7538 [0.6462, 0.8615]; brut 49/65 |
| pieces:12..15 | Scan200k | 65 | 1985 | 1694 | 291 | 0.8775 [0.8400, 0.9113]; brut 1486.5/1694 | 0.8308 [0.7385, 0.9231]; brut 54/65 |
| pieces:12..15 | Scan1M | 65 | 1985 | 1694 | 291 | 0.9463 [0.9274, 0.9628]; brut 1603/1694 | 0.9077 [0.8308, 0.9692]; brut 59/65 |
| pieces:16..19 | T0 | 63 | 3023 | 2962 | 61 | 0.5456 [0.5133, 0.5768]; brut 1616/2962 | 0.3016 [0.1905, 0.4127]; brut 19/63 |
| pieces:16..19 | D1 | 63 | 3023 | 2962 | 61 | 0.5695 [0.5315, 0.6066]; brut 1687/2962 | 0.1905 [0.0952, 0.2857]; brut 12/63 |
| pieces:16..19 | RF1 | 63 | 3023 | 2962 | 61 | 0.6111 [0.5593, 0.6632]; brut 1810/2962 | 0.2698 [0.1587, 0.3810]; brut 17/63 |
| pieces:16..19 | T3-A | 63 | 3023 | 2962 | 61 | 0.6188 [0.5750, 0.6607]; brut 1833/2962 | 0.3016 [0.1905, 0.4127]; brut 19/63 |
| pieces:16..19 | Jass1k | 63 | 3023 | 2962 | 61 | 0.6916 [0.6524, 0.7328]; brut 2048.5/2962 | 0.4444 [0.3175, 0.5714]; brut 28/63 |
| pieces:16..19 | Jass5k | 63 | 3023 | 2962 | 61 | 0.7237 [0.6860, 0.7597]; brut 2143.5/2962 | 0.4286 [0.3016, 0.5556]; brut 27/63 |
| pieces:16..19 | Jass50k | 63 | 3023 | 2962 | 61 | 0.7382 [0.6929, 0.7807]; brut 2186.5/2962 | 0.4127 [0.2857, 0.5397]; brut 26/63 |
| pieces:16..19 | Jass200k | 63 | 3023 | 2962 | 61 | 0.7703 [0.7349, 0.8042]; brut 2281.5/2962 | 0.4603 [0.3333, 0.5873]; brut 29/63 |
| pieces:16..19 | Jass1M | 63 | 3023 | 2962 | 61 | 0.7880 [0.7514, 0.8227]; brut 2334/2962 | 0.4762 [0.3492, 0.6032]; brut 30/63 |
| pieces:16..19 | Scan1k | 63 | 3023 | 2962 | 61 | 0.7819 [0.7524, 0.8118]; brut 2316/2962 | 0.4762 [0.3492, 0.6032]; brut 30/63 |
| pieces:16..19 | Scan5k | 63 | 3023 | 2962 | 61 | 0.8074 [0.7801, 0.8337]; brut 2391.5/2962 | 0.4921 [0.3651, 0.6190]; brut 31/63 |
| pieces:16..19 | Scan50k | 63 | 3023 | 2962 | 61 | 0.8327 [0.8074, 0.8582]; brut 2466.5/2962 | 0.6190 [0.4921, 0.7302]; brut 39/63 |
| pieces:16..19 | Scan200k | 63 | 3023 | 2962 | 61 | 0.8601 [0.8347, 0.8851]; brut 2547.5/2962 | 0.6190 [0.4921, 0.7302]; brut 39/63 |
| pieces:16..19 | Scan1M | 63 | 3023 | 2962 | 61 | 0.9166 [0.8999, 0.9329]; brut 2715/2962 | 0.7937 [0.6825, 0.8889]; brut 50/63 |
| pieces:20..24 | T0 | 73 | 4431 | 4363 | 68 | 0.5862 [0.5571, 0.6146]; brut 2557.5/4363 | 0.2192 [0.1233, 0.3151]; brut 16/73 |
| pieces:20..24 | D1 | 73 | 4431 | 4363 | 68 | 0.6172 [0.5881, 0.6441]; brut 2693/4363 | 0.1096 [0.0411, 0.1918]; brut 8/73 |
| pieces:20..24 | RF1 | 73 | 4431 | 4363 | 68 | 0.6594 [0.6296, 0.6870]; brut 2877/4363 | 0.2329 [0.1370, 0.3288]; brut 17/73 |
| pieces:20..24 | T3-A | 73 | 4431 | 4363 | 68 | 0.6450 [0.6186, 0.6706]; brut 2814/4363 | 0.2192 [0.1233, 0.3151]; brut 16/73 |
| pieces:20..24 | Jass1k | 73 | 4431 | 4363 | 68 | 0.7364 [0.7102, 0.7626]; brut 3213/4363 | 0.3014 [0.2055, 0.4110]; brut 22/73 |
| pieces:20..24 | Jass5k | 73 | 4431 | 4363 | 68 | 0.7556 [0.7270, 0.7836]; brut 3296.5/4363 | 0.3425 [0.2329, 0.4521]; brut 25/73 |
| pieces:20..24 | Jass50k | 73 | 4431 | 4363 | 68 | 0.7797 [0.7487, 0.8083]; brut 3402/4363 | 0.3973 [0.2877, 0.5068]; brut 29/73 |
| pieces:20..24 | Jass200k | 73 | 4431 | 4363 | 68 | 0.7925 [0.7649, 0.8193]; brut 3457.5/4363 | 0.3699 [0.2603, 0.4795]; brut 27/73 |
| pieces:20..24 | Jass1M | 73 | 4431 | 4363 | 68 | 0.8079 [0.7812, 0.8341]; brut 3525/4363 | 0.3836 [0.2740, 0.4932]; brut 28/73 |
| pieces:20..24 | Scan1k | 73 | 4431 | 4363 | 68 | 0.8213 [0.7974, 0.8443]; brut 3583.5/4363 | 0.3836 [0.2740, 0.4932]; brut 28/73 |
| pieces:20..24 | Scan5k | 73 | 4431 | 4363 | 68 | 0.8298 [0.8024, 0.8546]; brut 3620.5/4363 | 0.3699 [0.2603, 0.4795]; brut 27/73 |
| pieces:20..24 | Scan50k | 73 | 4431 | 4363 | 68 | 0.8592 [0.8406, 0.8759]; brut 3748.5/4363 | 0.4658 [0.3562, 0.5753]; brut 34/73 |
| pieces:20..24 | Scan200k | 73 | 4431 | 4363 | 68 | 0.8814 [0.8633, 0.8980]; brut 3845.5/4363 | 0.6164 [0.5068, 0.7260]; brut 45/73 |
| pieces:20..24 | Scan1M | 73 | 4431 | 4363 | 68 | 0.9204 [0.9091, 0.9311]; brut 4015.5/4363 | 0.5890 [0.4795, 0.6986]; brut 43/73 |
| pieces:25..29 | T0 | 55 | 3686 | 3590 | 96 | 0.5444 [0.5086, 0.5815]; brut 1954.5/3590 | 0.1818 [0.0909, 0.2909]; brut 10/55 |
| pieces:25..29 | D1 | 55 | 3686 | 3590 | 96 | 0.6114 [0.5737, 0.6460]; brut 2195/3590 | 0.2545 [0.1455, 0.3818]; brut 14/55 |
| pieces:25..29 | RF1 | 55 | 3686 | 3590 | 96 | 0.6292 [0.5890, 0.6664]; brut 2259/3590 | 0.2182 [0.1091, 0.3273]; brut 12/55 |
| pieces:25..29 | T3-A | 55 | 3686 | 3590 | 96 | 0.6231 [0.5806, 0.6639]; brut 2237/3590 | 0.2000 [0.1091, 0.3091]; brut 11/55 |
| pieces:25..29 | Jass1k | 55 | 3686 | 3590 | 96 | 0.7214 [0.6825, 0.7588]; brut 2590/3590 | 0.3636 [0.2364, 0.4909]; brut 20/55 |
| pieces:25..29 | Jass5k | 55 | 3686 | 3590 | 96 | 0.7634 [0.7376, 0.7898]; brut 2740.5/3590 | 0.3636 [0.2364, 0.4909]; brut 20/55 |
| pieces:25..29 | Jass50k | 55 | 3686 | 3590 | 96 | 0.7876 [0.7623, 0.8120]; brut 2827.5/3590 | 0.3818 [0.2545, 0.5091]; brut 21/55 |
| pieces:25..29 | Jass200k | 55 | 3686 | 3590 | 96 | 0.8072 [0.7819, 0.8322]; brut 2898/3590 | 0.5273 [0.4000, 0.6545]; brut 29/55 |
| pieces:25..29 | Jass1M | 55 | 3686 | 3590 | 96 | 0.8223 [0.7957, 0.8479]; brut 2952/3590 | 0.4727 [0.3455, 0.6000]; brut 26/55 |
| pieces:25..29 | Scan1k | 55 | 3686 | 3590 | 96 | 0.8528 [0.8262, 0.8775]; brut 3061.5/3590 | 0.4727 [0.3455, 0.6000]; brut 26/55 |
| pieces:25..29 | Scan5k | 55 | 3686 | 3590 | 96 | 0.8586 [0.8389, 0.8777]; brut 3082.5/3590 | 0.5091 [0.3818, 0.6364]; brut 28/55 |
| pieces:25..29 | Scan50k | 55 | 3686 | 3590 | 96 | 0.8997 [0.8828, 0.9155]; brut 3230/3590 | 0.5636 [0.4364, 0.6909]; brut 31/55 |
| pieces:25..29 | Scan200k | 55 | 3686 | 3590 | 96 | 0.9135 [0.8981, 0.9280]; brut 3279.5/3590 | 0.6909 [0.5636, 0.8182]; brut 38/55 |
| pieces:25..29 | Scan1M | 55 | 3686 | 3590 | 96 | 0.9347 [0.9228, 0.9459]; brut 3355.5/3590 | 0.6182 [0.4909, 0.7455]; brut 34/55 |
| pieces:30..34 | T0 | 72 | 4542 | 4382 | 160 | 0.5956 [0.5695, 0.6210]; brut 2610/4382 | 0.2361 [0.1389, 0.3333]; brut 17/72 |
| pieces:30..34 | D1 | 72 | 4542 | 4382 | 160 | 0.6301 [0.6032, 0.6555]; brut 2761/4382 | 0.2639 [0.1667, 0.3611]; brut 19/72 |
| pieces:30..34 | RF1 | 72 | 4542 | 4382 | 160 | 0.6634 [0.6337, 0.6921]; brut 2907/4382 | 0.2361 [0.1389, 0.3333]; brut 17/72 |
| pieces:30..34 | T3-A | 72 | 4542 | 4382 | 160 | 0.6333 [0.6068, 0.6581]; brut 2775/4382 | 0.2639 [0.1667, 0.3750]; brut 19/72 |
| pieces:30..34 | Jass1k | 72 | 4542 | 4382 | 160 | 0.7522 [0.7216, 0.7799]; brut 3296/4382 | 0.3889 [0.2778, 0.5000]; brut 28/72 |
| pieces:30..34 | Jass5k | 72 | 4542 | 4382 | 160 | 0.7907 [0.7653, 0.8148]; brut 3465/4382 | 0.4306 [0.3194, 0.5417]; brut 31/72 |
| pieces:30..34 | Jass50k | 72 | 4542 | 4382 | 160 | 0.8018 [0.7777, 0.8246]; brut 3513.5/4382 | 0.4306 [0.3194, 0.5417]; brut 31/72 |
| pieces:30..34 | Jass200k | 72 | 4542 | 4382 | 160 | 0.8172 [0.7934, 0.8393]; brut 3581/4382 | 0.5556 [0.4444, 0.6667]; brut 40/72 |
| pieces:30..34 | Jass1M | 72 | 4542 | 4382 | 160 | 0.8241 [0.7977, 0.8481]; brut 3611/4382 | 0.4722 [0.3611, 0.5833]; brut 34/72 |
| pieces:30..34 | Scan1k | 72 | 4542 | 4382 | 160 | 0.8542 [0.8350, 0.8721]; brut 3743/4382 | 0.4306 [0.3194, 0.5417]; brut 31/72 |
| pieces:30..34 | Scan5k | 72 | 4542 | 4382 | 160 | 0.8686 [0.8466, 0.8886]; brut 3806/4382 | 0.4861 [0.3750, 0.5972]; brut 35/72 |
| pieces:30..34 | Scan50k | 72 | 4542 | 4382 | 160 | 0.9005 [0.8860, 0.9136]; brut 3946/4382 | 0.6528 [0.5417, 0.7639]; brut 47/72 |
| pieces:30..34 | Scan200k | 72 | 4542 | 4382 | 160 | 0.9135 [0.8986, 0.9274]; brut 4003/4382 | 0.6528 [0.5417, 0.7639]; brut 47/72 |
| pieces:30..34 | Scan1M | 72 | 4542 | 4382 | 160 | 0.9351 [0.9218, 0.9469]; brut 4097.5/4382 | 0.6111 [0.5000, 0.7222]; brut 44/72 |
| pieces:35..40 | T0 | 56 | 2716 | 2644 | 72 | 0.6541 [0.6203, 0.6878]; brut 1729.5/2644 | 0.1964 [0.1071, 0.3036]; brut 11/56 |
| pieces:35..40 | D1 | 56 | 2716 | 2644 | 72 | 0.6415 [0.5972, 0.6823]; brut 1696/2644 | 0.2321 [0.1250, 0.3393]; brut 13/56 |
| pieces:35..40 | RF1 | 56 | 2716 | 2644 | 72 | 0.7296 [0.6948, 0.7615]; brut 1929/2644 | 0.2500 [0.1429, 0.3750]; brut 14/56 |
| pieces:35..40 | T3-A | 56 | 2716 | 2644 | 72 | 0.6955 [0.6611, 0.7301]; brut 1839/2644 | 0.1964 [0.1071, 0.3036]; brut 11/56 |
| pieces:35..40 | Jass1k | 56 | 2716 | 2644 | 72 | 0.8272 [0.7976, 0.8543]; brut 2187/2644 | 0.5000 [0.3750, 0.6250]; brut 28/56 |
| pieces:35..40 | Jass5k | 56 | 2716 | 2644 | 72 | 0.8406 [0.8172, 0.8624]; brut 2222.5/2644 | 0.5000 [0.3750, 0.6250]; brut 28/56 |
| pieces:35..40 | Jass50k | 56 | 2716 | 2644 | 72 | 0.8599 [0.8350, 0.8833]; brut 2273.5/2644 | 0.6250 [0.5000, 0.7500]; brut 35/56 |
| pieces:35..40 | Jass200k | 56 | 2716 | 2644 | 72 | 0.8604 [0.8395, 0.8799]; brut 2275/2644 | 0.5893 [0.4643, 0.7143]; brut 33/56 |
| pieces:35..40 | Jass1M | 56 | 2716 | 2644 | 72 | 0.8599 [0.8374, 0.8808]; brut 2273.5/2644 | 0.5179 [0.3929, 0.6429]; brut 29/56 |
| pieces:35..40 | Scan1k | 56 | 2716 | 2644 | 72 | 0.8873 [0.8724, 0.9011]; brut 2346/2644 | 0.5536 [0.4286, 0.6786]; brut 31/56 |
| pieces:35..40 | Scan5k | 56 | 2716 | 2644 | 72 | 0.9030 [0.8868, 0.9183]; brut 2387.5/2644 | 0.7143 [0.5893, 0.8214]; brut 40/56 |
| pieces:35..40 | Scan50k | 56 | 2716 | 2644 | 72 | 0.9217 [0.9070, 0.9349]; brut 2437/2644 | 0.6964 [0.5714, 0.8214]; brut 39/56 |
| pieces:35..40 | Scan200k | 56 | 2716 | 2644 | 72 | 0.9323 [0.9187, 0.9450]; brut 2465/2644 | 0.7500 [0.6250, 0.8571]; brut 42/56 |
| pieces:35..40 | Scan1M | 56 | 2716 | 2644 | 72 | 0.9580 [0.9499, 0.9657]; brut 2533/2644 | 0.7679 [0.6607, 0.8750]; brut 43/56 |

### ULTRA256

| Strate | Signal | Parents | Pairs totaux | Pairs comparables | Ties référence | Pairwise | Top-hit |
|---|---|---:|---:|---:|---:|---:|---:|
| phase:P0 | T0 | 64 | 3835 | 3707 | 128 | 0.6035 [0.5714, 0.6349]; brut 2237/3707 | 0.1094 [0.0469, 0.1875]; brut 7/64 |
| phase:P0 | D1 | 64 | 3835 | 3707 | 128 | 0.6113 [0.5762, 0.6439]; brut 2266/3707 | 0.2188 [0.1250, 0.3281]; brut 14/64 |
| phase:P0 | RF1 | 64 | 3835 | 3707 | 128 | 0.6561 [0.6245, 0.6860]; brut 2432/3707 | 0.2344 [0.1406, 0.3438]; brut 15/64 |
| phase:P0 | T3-A | 64 | 3835 | 3707 | 128 | 0.6280 [0.5987, 0.6559]; brut 2328/3707 | 0.1406 [0.0625, 0.2344]; brut 9/64 |
| phase:P0 | Jass1k | 64 | 3835 | 3707 | 128 | 0.7722 [0.7420, 0.7999]; brut 2862.5/3707 | 0.4844 [0.3594, 0.6094]; brut 31/64 |
| phase:P0 | Jass5k | 64 | 3835 | 3707 | 128 | 0.8031 [0.7763, 0.8282]; brut 2977/3707 | 0.4375 [0.3125, 0.5625]; brut 28/64 |
| phase:P0 | Jass50k | 64 | 3835 | 3707 | 128 | 0.8025 [0.7753, 0.8281]; brut 2975/3707 | 0.3594 [0.2500, 0.4844]; brut 23/64 |
| phase:P0 | Jass200k | 64 | 3835 | 3707 | 128 | 0.8114 [0.7853, 0.8355]; brut 3008/3707 | 0.3750 [0.2656, 0.5000]; brut 24/64 |
| phase:P0 | Jass1M | 64 | 3835 | 3707 | 128 | 0.8198 [0.7936, 0.8435]; brut 3039/3707 | 0.4062 [0.2812, 0.5312]; brut 26/64 |
| phase:P0 | Scan1k | 64 | 3835 | 3707 | 128 | 0.8562 [0.8357, 0.8747]; brut 3174/3707 | 0.4531 [0.3281, 0.5781]; brut 29/64 |
| phase:P0 | Scan5k | 64 | 3835 | 3707 | 128 | 0.8708 [0.8467, 0.8923]; brut 3228/3707 | 0.5469 [0.4219, 0.6719]; brut 35/64 |
| phase:P0 | Scan50k | 64 | 3835 | 3707 | 128 | 0.8956 [0.8793, 0.9100]; brut 3320/3707 | 0.5312 [0.4062, 0.6562]; brut 34/64 |
| phase:P0 | Scan200k | 64 | 3835 | 3707 | 128 | 0.9010 [0.8828, 0.9178]; brut 3340/3707 | 0.5781 [0.4531, 0.7031]; brut 37/64 |
| phase:P0 | Scan1M | 64 | 3835 | 3707 | 128 | 0.9196 [0.9059, 0.9324]; brut 3409/3707 | 0.5000 [0.3750, 0.6250]; brut 32/64 |
| phase:P0 | Scan2M | 64 | 3835 | 3707 | 128 | 0.9270 [0.9111, 0.9414]; brut 3436.5/3707 | 0.6250 [0.5000, 0.7344]; brut 40/64 |
| phase:P1 | T0 | 64 | 4269 | 4183 | 86 | 0.5417 [0.5105, 0.5734]; brut 2266/4183 | 0.1875 [0.0938, 0.2812]; brut 12/64 |
| phase:P1 | D1 | 64 | 4269 | 4183 | 86 | 0.6228 [0.5946, 0.6499]; brut 2605/4183 | 0.2031 [0.1094, 0.3125]; brut 13/64 |
| phase:P1 | RF1 | 64 | 4269 | 4183 | 86 | 0.6431 [0.6084, 0.6753]; brut 2690/4183 | 0.1562 [0.0781, 0.2500]; brut 10/64 |
| phase:P1 | T3-A | 64 | 4269 | 4183 | 86 | 0.6302 [0.5941, 0.6648]; brut 2636/4183 | 0.1875 [0.0938, 0.2812]; brut 12/64 |
| phase:P1 | Jass1k | 64 | 4269 | 4183 | 86 | 0.7360 [0.7029, 0.7688]; brut 3078.5/4183 | 0.2969 [0.1875, 0.4062]; brut 19/64 |
| phase:P1 | Jass5k | 64 | 4269 | 4183 | 86 | 0.7553 [0.7269, 0.7846]; brut 3159.5/4183 | 0.3281 [0.2188, 0.4531]; brut 21/64 |
| phase:P1 | Jass50k | 64 | 4269 | 4183 | 86 | 0.7850 [0.7532, 0.8131]; brut 3283.5/4183 | 0.3125 [0.2031, 0.4219]; brut 20/64 |
| phase:P1 | Jass200k | 64 | 4269 | 4183 | 86 | 0.8067 [0.7785, 0.8337]; brut 3374.5/4183 | 0.4062 [0.2812, 0.5312]; brut 26/64 |
| phase:P1 | Jass1M | 64 | 4269 | 4183 | 86 | 0.8174 [0.7864, 0.8468]; brut 3419/4183 | 0.4219 [0.2969, 0.5469]; brut 27/64 |
| phase:P1 | Scan1k | 64 | 4269 | 4183 | 86 | 0.8237 [0.7978, 0.8488]; brut 3445.5/4183 | 0.3125 [0.2031, 0.4219]; brut 20/64 |
| phase:P1 | Scan5k | 64 | 4269 | 4183 | 86 | 0.8395 [0.8132, 0.8634]; brut 3511.5/4183 | 0.4062 [0.2812, 0.5312]; brut 26/64 |
| phase:P1 | Scan50k | 64 | 4269 | 4183 | 86 | 0.8705 [0.8516, 0.8885]; brut 3641.5/4183 | 0.5000 [0.3750, 0.6250]; brut 32/64 |
| phase:P1 | Scan200k | 64 | 4269 | 4183 | 86 | 0.8906 [0.8714, 0.9084]; brut 3725.5/4183 | 0.5781 [0.4531, 0.7031]; brut 37/64 |
| phase:P1 | Scan1M | 64 | 4269 | 4183 | 86 | 0.9108 [0.8964, 0.9248]; brut 3810/4183 | 0.5938 [0.4688, 0.7188]; brut 38/64 |
| phase:P1 | Scan2M | 64 | 4269 | 4183 | 86 | 0.9270 [0.9137, 0.9395]; brut 3877.5/4183 | 0.5938 [0.4688, 0.7188]; brut 38/64 |
| phase:P2 | T0 | 64 | 2440 | 2332 | 108 | 0.5742 [0.5366, 0.6076]; brut 1339/2332 | 0.3438 [0.2344, 0.4688]; brut 22/64 |
| phase:P2 | D1 | 64 | 2440 | 2332 | 108 | 0.5686 [0.5315, 0.6050]; brut 1326/2332 | 0.2812 [0.1719, 0.3906]; brut 18/64 |
| phase:P2 | RF1 | 64 | 2440 | 2332 | 108 | 0.6132 [0.5652, 0.6624]; brut 1430/2332 | 0.2656 [0.1562, 0.3750]; brut 17/64 |
| phase:P2 | T3-A | 64 | 2440 | 2332 | 108 | 0.6196 [0.5638, 0.6718]; brut 1445/2332 | 0.3750 [0.2656, 0.5000]; brut 24/64 |
| phase:P2 | Jass1k | 64 | 2440 | 2332 | 108 | 0.6829 [0.6432, 0.7253]; brut 1592.5/2332 | 0.4062 [0.2812, 0.5312]; brut 26/64 |
| phase:P2 | Jass5k | 64 | 2440 | 2332 | 108 | 0.7286 [0.6963, 0.7613]; brut 1699/2332 | 0.4531 [0.3281, 0.5781]; brut 29/64 |
| phase:P2 | Jass50k | 64 | 2440 | 2332 | 108 | 0.7256 [0.6814, 0.7689]; brut 1692/2332 | 0.4531 [0.3281, 0.5781]; brut 29/64 |
| phase:P2 | Jass200k | 64 | 2440 | 2332 | 108 | 0.7573 [0.7129, 0.8003]; brut 1766/2332 | 0.5000 [0.3750, 0.6250]; brut 32/64 |
| phase:P2 | Jass1M | 64 | 2440 | 2332 | 108 | 0.7650 [0.7179, 0.8099]; brut 1784/2332 | 0.5312 [0.4062, 0.6562]; brut 34/64 |
| phase:P2 | Scan1k | 64 | 2440 | 2332 | 108 | 0.7742 [0.7443, 0.8048]; brut 1805.5/2332 | 0.4531 [0.3281, 0.5781]; brut 29/64 |
| phase:P2 | Scan5k | 64 | 2440 | 2332 | 108 | 0.7993 [0.7747, 0.8251]; brut 1864/2332 | 0.5781 [0.4531, 0.7031]; brut 37/64 |
| phase:P2 | Scan50k | 64 | 2440 | 2332 | 108 | 0.8242 [0.7882, 0.8594]; brut 1922/2332 | 0.6562 [0.5312, 0.7656]; brut 42/64 |
| phase:P2 | Scan200k | 64 | 2440 | 2332 | 108 | 0.8568 [0.8290, 0.8847]; brut 1998/2332 | 0.6875 [0.5781, 0.7969]; brut 44/64 |
| phase:P2 | Scan1M | 64 | 2440 | 2332 | 108 | 0.8934 [0.8715, 0.9150]; brut 2083.5/2332 | 0.7656 [0.6562, 0.8594]; brut 49/64 |
| phase:P2 | Scan2M | 64 | 2440 | 2332 | 108 | 0.9198 [0.8973, 0.9405]; brut 2145/2332 | 0.8281 [0.7344, 0.9219]; brut 53/64 |
| phase:P3 | T0 | 64 | 2041 | 1347 | 694 | 0.5471 [0.4889, 0.6022]; brut 737/1347 | 0.4688 [0.3438, 0.5938]; brut 30/64 |
| phase:P3 | D1 | 64 | 2041 | 1347 | 694 | 0.5501 [0.4922, 0.6071]; brut 741/1347 | 0.3750 [0.2656, 0.5000]; brut 24/64 |
| phase:P3 | RF1 | 64 | 2041 | 1347 | 694 | 0.6889 [0.6337, 0.7418]; brut 928/1347 | 0.4688 [0.3438, 0.5938]; brut 30/64 |
| phase:P3 | T3-A | 64 | 2041 | 1347 | 694 | 0.6221 [0.5450, 0.6887]; brut 838/1347 | 0.4688 [0.3438, 0.5938]; brut 30/64 |
| phase:P3 | Jass1k | 64 | 2041 | 1347 | 694 | 0.7610 [0.6979, 0.8158]; brut 1025/1347 | 0.6875 [0.5781, 0.7969]; brut 44/64 |
| phase:P3 | Jass5k | 64 | 2041 | 1347 | 694 | 0.7773 [0.7066, 0.8351]; brut 1047/1347 | 0.6250 [0.5000, 0.7344]; brut 40/64 |
| phase:P3 | Jass50k | 64 | 2041 | 1347 | 694 | 0.7732 [0.7116, 0.8312]; brut 1041.5/1347 | 0.6094 [0.4844, 0.7344]; brut 39/64 |
| phase:P3 | Jass200k | 64 | 2041 | 1347 | 694 | 0.7558 [0.6970, 0.8145]; brut 1018/1347 | 0.5938 [0.4688, 0.7188]; brut 38/64 |
| phase:P3 | Jass1M | 64 | 2041 | 1347 | 694 | 0.7684 [0.7120, 0.8232]; brut 1035/1347 | 0.6250 [0.5000, 0.7344]; brut 40/64 |
| phase:P3 | Scan1k | 64 | 2041 | 1347 | 694 | 0.8393 [0.7830, 0.8884]; brut 1130.5/1347 | 0.7969 [0.6875, 0.8906]; brut 51/64 |
| phase:P3 | Scan5k | 64 | 2041 | 1347 | 694 | 0.8255 [0.7523, 0.8889]; brut 1112/1347 | 0.7812 [0.6719, 0.8750]; brut 50/64 |
| phase:P3 | Scan50k | 64 | 2041 | 1347 | 694 | 0.8608 [0.8029, 0.9105]; brut 1159.5/1347 | 0.8281 [0.7344, 0.9219]; brut 53/64 |
| phase:P3 | Scan200k | 64 | 2041 | 1347 | 694 | 0.8953 [0.8514, 0.9333]; brut 1206/1347 | 0.8281 [0.7344, 0.9219]; brut 53/64 |
| phase:P3 | Scan1M | 64 | 2041 | 1347 | 694 | 0.9217 [0.8896, 0.9501]; brut 1241.5/1347 | 0.8906 [0.8125, 0.9531]; brut 57/64 |
| phase:P3 | Scan2M | 64 | 2041 | 1347 | 694 | 0.9302 [0.8980, 0.9569]; brut 1253/1347 | 0.9219 [0.8438, 0.9844]; brut 59/64 |
| colour:white | T0 | 125 | 6199 | 5767 | 432 | 0.5703 [0.5415, 0.5980]; brut 3289/5767 | 0.2320 [0.1600, 0.3120]; brut 29/125 |
| colour:white | D1 | 125 | 6199 | 5767 | 432 | 0.6019 [0.5762, 0.6263]; brut 3471/5767 | 0.2240 [0.1520, 0.2960]; brut 28/125 |
| colour:white | RF1 | 125 | 6199 | 5767 | 432 | 0.6516 [0.6241, 0.6782]; brut 3758/5767 | 0.2560 [0.1840, 0.3360]; brut 32/125 |
| colour:white | T3-A | 125 | 6199 | 5767 | 432 | 0.6319 [0.6007, 0.6613]; brut 3644/5767 | 0.2640 [0.1920, 0.3440]; brut 33/125 |
| colour:white | Jass1k | 125 | 6199 | 5767 | 432 | 0.7358 [0.7062, 0.7648]; brut 4243.5/5767 | 0.4480 [0.3600, 0.5360]; brut 56/125 |
| colour:white | Jass5k | 125 | 6199 | 5767 | 432 | 0.7729 [0.7476, 0.7975]; brut 4457.5/5767 | 0.4480 [0.3600, 0.5360]; brut 56/125 |
| colour:white | Jass50k | 125 | 6199 | 5767 | 432 | 0.7717 [0.7456, 0.7969]; brut 4450.5/5767 | 0.4480 [0.3600, 0.5360]; brut 56/125 |
| colour:white | Jass200k | 125 | 6199 | 5767 | 432 | 0.7948 [0.7696, 0.8191]; brut 4583.5/5767 | 0.4960 [0.4080, 0.5840]; brut 62/125 |
| colour:white | Jass1M | 125 | 6199 | 5767 | 432 | 0.8089 [0.7836, 0.8329]; brut 4665/5767 | 0.4880 [0.4000, 0.5760]; brut 61/125 |
| colour:white | Scan1k | 125 | 6199 | 5767 | 432 | 0.8331 [0.8116, 0.8537]; brut 4804.5/5767 | 0.4800 [0.3920, 0.5680]; brut 60/125 |
| colour:white | Scan5k | 125 | 6199 | 5767 | 432 | 0.8408 [0.8196, 0.8609]; brut 4849/5767 | 0.5840 [0.4960, 0.6720]; brut 73/125 |
| colour:white | Scan50k | 125 | 6199 | 5767 | 432 | 0.8709 [0.8507, 0.8897]; brut 5022.5/5767 | 0.6640 [0.5840, 0.7440]; brut 83/125 |
| colour:white | Scan200k | 125 | 6199 | 5767 | 432 | 0.8845 [0.8667, 0.9013]; brut 5101/5767 | 0.6880 [0.6080, 0.7680]; brut 86/125 |
| colour:white | Scan1M | 125 | 6199 | 5767 | 432 | 0.9133 [0.8998, 0.9262]; brut 5267/5767 | 0.7120 [0.6320, 0.7920]; brut 89/125 |
| colour:white | Scan2M | 125 | 6199 | 5767 | 432 | 0.9253 [0.9118, 0.9377]; brut 5336/5767 | 0.8080 [0.7360, 0.8720]; brut 101/125 |
| colour:black | T0 | 131 | 6386 | 5802 | 584 | 0.5670 [0.5428, 0.5914]; brut 3290/5802 | 0.3206 [0.2443, 0.4046]; brut 42/131 |
| colour:black | D1 | 131 | 6386 | 5802 | 584 | 0.5976 [0.5701, 0.6240]; brut 3467/5802 | 0.3130 [0.2366, 0.3969]; brut 41/131 |
| colour:black | RF1 | 131 | 6386 | 5802 | 584 | 0.6415 [0.6117, 0.6701]; brut 3722/5802 | 0.3053 [0.2290, 0.3817]; brut 40/131 |
| colour:black | T3-A | 131 | 6386 | 5802 | 584 | 0.6210 [0.5917, 0.6491]; brut 3603/5802 | 0.3206 [0.2443, 0.4046]; brut 42/131 |
| colour:black | Jass1k | 131 | 6386 | 5802 | 584 | 0.7437 [0.7176, 0.7692]; brut 4315/5802 | 0.4885 [0.4046, 0.5725]; brut 64/131 |
| colour:black | Jass5k | 131 | 6386 | 5802 | 584 | 0.7627 [0.7383, 0.7865]; brut 4425/5802 | 0.4733 [0.3893, 0.5573]; brut 62/131 |
| colour:black | Jass50k | 131 | 6386 | 5802 | 584 | 0.7827 [0.7555, 0.8078]; brut 4541.5/5802 | 0.4198 [0.3359, 0.5038]; brut 55/131 |
| colour:black | Jass200k | 131 | 6386 | 5802 | 584 | 0.7899 [0.7648, 0.8137]; brut 4583/5802 | 0.4427 [0.3588, 0.5267]; brut 58/131 |
| colour:black | Jass1M | 131 | 6386 | 5802 | 584 | 0.7949 [0.7678, 0.8205]; brut 4612/5802 | 0.5038 [0.4198, 0.5878]; brut 66/131 |
| colour:black | Scan1k | 131 | 6386 | 5802 | 584 | 0.8189 [0.7979, 0.8391]; brut 4751/5802 | 0.5267 [0.4427, 0.6107]; brut 69/131 |
| colour:black | Scan5k | 131 | 6386 | 5802 | 584 | 0.8388 [0.8147, 0.8609]; brut 4866.5/5802 | 0.5725 [0.4885, 0.6565]; brut 75/131 |
| colour:black | Scan50k | 131 | 6386 | 5802 | 584 | 0.8653 [0.8465, 0.8827]; brut 5020.5/5802 | 0.5954 [0.5115, 0.6794]; brut 78/131 |
| colour:black | Scan200k | 131 | 6386 | 5802 | 584 | 0.8908 [0.8744, 0.9063]; brut 5168.5/5802 | 0.6489 [0.5649, 0.7328]; brut 85/131 |
| colour:black | Scan1M | 131 | 6386 | 5802 | 584 | 0.9095 [0.8972, 0.9213]; brut 5277/5802 | 0.6641 [0.5802, 0.7405]; brut 87/131 |
| colour:black | Scan2M | 131 | 6386 | 5802 | 584 | 0.9266 [0.9145, 0.9380]; brut 5376/5802 | 0.6794 [0.5954, 0.7557]; brut 89/131 |
| branching:2..4 | T0 | 41 | 105 | 68 | 37 | 0.5588 [0.3962, 0.6897]; brut 38/68 | 0.6098 [0.4634, 0.7561]; brut 25/41 |
| branching:2..4 | D1 | 41 | 105 | 68 | 37 | 0.6029 [0.4444, 0.7500]; brut 41/68 | 0.7561 [0.6098, 0.8780]; brut 31/41 |
| branching:2..4 | RF1 | 41 | 105 | 68 | 37 | 0.6176 [0.4490, 0.7746]; brut 42/68 | 0.6585 [0.5122, 0.8049]; brut 27/41 |
| branching:2..4 | T3-A | 41 | 105 | 68 | 37 | 0.6324 [0.4746, 0.7639]; brut 43/68 | 0.6585 [0.5122, 0.8049]; brut 27/41 |
| branching:2..4 | Jass1k | 41 | 105 | 68 | 37 | 0.7794 [0.6609, 0.8828]; brut 53/68 | 0.7805 [0.6585, 0.9024]; brut 32/41 |
| branching:2..4 | Jass5k | 41 | 105 | 68 | 37 | 0.7206 [0.5962, 0.8424]; brut 49/68 | 0.7561 [0.6098, 0.8780]; brut 31/41 |
| branching:2..4 | Jass50k | 41 | 105 | 68 | 37 | 0.7500 [0.6364, 0.8627]; brut 51/68 | 0.7561 [0.6098, 0.8780]; brut 31/41 |
| branching:2..4 | Jass200k | 41 | 105 | 68 | 37 | 0.7794 [0.6765, 0.8824]; brut 53/68 | 0.7805 [0.6585, 0.9024]; brut 32/41 |
| branching:2..4 | Jass1M | 41 | 105 | 68 | 37 | 0.7868 [0.6818, 0.8824]; brut 53.5/68 | 0.7805 [0.6585, 0.9024]; brut 32/41 |
| branching:2..4 | Scan1k | 41 | 105 | 68 | 37 | 0.8529 [0.7500, 0.9375]; brut 58/68 | 0.8537 [0.7317, 0.9512]; brut 35/41 |
| branching:2..4 | Scan5k | 41 | 105 | 68 | 37 | 0.8456 [0.7453, 0.9362]; brut 57.5/68 | 0.8537 [0.7317, 0.9512]; brut 35/41 |
| branching:2..4 | Scan50k | 41 | 105 | 68 | 37 | 0.8676 [0.7500, 0.9595]; brut 59/68 | 0.8780 [0.7805, 0.9756]; brut 36/41 |
| branching:2..4 | Scan200k | 41 | 105 | 68 | 37 | 0.9412 [0.8750, 1.0000]; brut 64/68 | 0.9268 [0.8293, 1.0000]; brut 38/41 |
| branching:2..4 | Scan1M | 41 | 105 | 68 | 37 | 0.8971 [0.8033, 0.9767]; brut 61/68 | 0.8780 [0.7805, 0.9756]; brut 36/41 |
| branching:2..4 | Scan2M | 41 | 105 | 68 | 37 | 0.9265 [0.8529, 0.9855]; brut 63/68 | 0.9024 [0.8049, 0.9756]; brut 37/41 |
| branching:5..8 | T0 | 51 | 988 | 901 | 87 | 0.5067 [0.4570, 0.5544]; brut 456.5/901 | 0.2549 [0.1373, 0.3725]; brut 13/51 |
| branching:5..8 | D1 | 51 | 988 | 901 | 87 | 0.5871 [0.5362, 0.6373]; brut 529/901 | 0.2353 [0.1176, 0.3529]; brut 12/51 |
| branching:5..8 | RF1 | 51 | 988 | 901 | 87 | 0.6903 [0.6433, 0.7362]; brut 622/901 | 0.2745 [0.1569, 0.3922]; brut 14/51 |
| branching:5..8 | T3-A | 51 | 988 | 901 | 87 | 0.6448 [0.5921, 0.6962]; brut 581/901 | 0.3529 [0.2157, 0.4902]; brut 18/51 |
| branching:5..8 | Jass1k | 51 | 988 | 901 | 87 | 0.7120 [0.6586, 0.7618]; brut 641.5/901 | 0.3922 [0.2549, 0.5294]; brut 20/51 |
| branching:5..8 | Jass5k | 51 | 988 | 901 | 87 | 0.7364 [0.6921, 0.7762]; brut 663.5/901 | 0.3333 [0.2157, 0.4706]; brut 17/51 |
| branching:5..8 | Jass50k | 51 | 988 | 901 | 87 | 0.7259 [0.6724, 0.7732]; brut 654/901 | 0.3333 [0.2157, 0.4706]; brut 17/51 |
| branching:5..8 | Jass200k | 51 | 988 | 901 | 87 | 0.7314 [0.6751, 0.7823]; brut 659/901 | 0.3725 [0.2353, 0.5098]; brut 19/51 |
| branching:5..8 | Jass1M | 51 | 988 | 901 | 87 | 0.7353 [0.6743, 0.7891]; brut 662.5/901 | 0.4118 [0.2745, 0.5490]; brut 21/51 |
| branching:5..8 | Scan1k | 51 | 988 | 901 | 87 | 0.7997 [0.7530, 0.8405]; brut 720.5/901 | 0.4510 [0.3137, 0.5882]; brut 23/51 |
| branching:5..8 | Scan5k | 51 | 988 | 901 | 87 | 0.8257 [0.7943, 0.8557]; brut 744/901 | 0.6667 [0.5294, 0.7843]; brut 34/51 |
| branching:5..8 | Scan50k | 51 | 988 | 901 | 87 | 0.8618 [0.8282, 0.8913]; brut 776.5/901 | 0.7059 [0.5686, 0.8235]; brut 36/51 |
| branching:5..8 | Scan200k | 51 | 988 | 901 | 87 | 0.8868 [0.8564, 0.9140]; brut 799/901 | 0.7059 [0.5686, 0.8235]; brut 36/51 |
| branching:5..8 | Scan1M | 51 | 988 | 901 | 87 | 0.9151 [0.8891, 0.9376]; brut 824.5/901 | 0.8039 [0.6863, 0.9020]; brut 41/51 |
| branching:5..8 | Scan2M | 51 | 988 | 901 | 87 | 0.9373 [0.9207, 0.9527]; brut 844.5/901 | 0.8431 [0.7451, 0.9412]; brut 43/51 |
| branching:9..12 | T0 | 95 | 5019 | 4770 | 249 | 0.5803 [0.5534, 0.6065]; brut 2768/4770 | 0.2000 [0.1263, 0.2842]; brut 19/95 |
| branching:9..12 | D1 | 95 | 5019 | 4770 | 249 | 0.5971 [0.5695, 0.6235]; brut 2848/4770 | 0.1263 [0.0632, 0.2000]; brut 12/95 |
| branching:9..12 | RF1 | 95 | 5019 | 4770 | 249 | 0.6415 [0.6139, 0.6678]; brut 3060/4770 | 0.1474 [0.0842, 0.2211]; brut 14/95 |
| branching:9..12 | T3-A | 95 | 5019 | 4770 | 249 | 0.6304 [0.6004, 0.6589]; brut 3007/4770 | 0.2000 [0.1263, 0.2842]; brut 19/95 |
| branching:9..12 | Jass1k | 95 | 5019 | 4770 | 249 | 0.7432 [0.7171, 0.7683]; brut 3545/4770 | 0.3684 [0.2737, 0.4632]; brut 35/95 |
| branching:9..12 | Jass5k | 95 | 5019 | 4770 | 249 | 0.7715 [0.7479, 0.7950]; brut 3680/4770 | 0.3474 [0.2526, 0.4421]; brut 33/95 |
| branching:9..12 | Jass50k | 95 | 5019 | 4770 | 249 | 0.7876 [0.7650, 0.8098]; brut 3757/4770 | 0.3158 [0.2211, 0.4105]; brut 30/95 |
| branching:9..12 | Jass200k | 95 | 5019 | 4770 | 249 | 0.8016 [0.7789, 0.8233]; brut 3823.5/4770 | 0.3579 [0.2632, 0.4526]; brut 34/95 |
| branching:9..12 | Jass1M | 95 | 5019 | 4770 | 249 | 0.8093 [0.7863, 0.8316]; brut 3860.5/4770 | 0.3789 [0.2842, 0.4737]; brut 36/95 |
| branching:9..12 | Scan1k | 95 | 5019 | 4770 | 249 | 0.8362 [0.8172, 0.8541]; brut 3988.5/4770 | 0.4316 [0.3368, 0.5368]; brut 41/95 |
| branching:9..12 | Scan5k | 95 | 5019 | 4770 | 249 | 0.8419 [0.8213, 0.8614]; brut 4016/4770 | 0.4526 [0.3579, 0.5579]; brut 43/95 |
| branching:9..12 | Scan50k | 95 | 5019 | 4770 | 249 | 0.8645 [0.8438, 0.8834]; brut 4123.5/4770 | 0.4737 [0.3789, 0.5789]; brut 45/95 |
| branching:9..12 | Scan200k | 95 | 5019 | 4770 | 249 | 0.8840 [0.8671, 0.8999]; brut 4216.5/4770 | 0.5474 [0.4421, 0.6421]; brut 52/95 |
| branching:9..12 | Scan1M | 95 | 5019 | 4770 | 249 | 0.9099 [0.8976, 0.9216]; brut 4340/4770 | 0.5368 [0.4316, 0.6316]; brut 51/95 |
| branching:9..12 | Scan2M | 95 | 5019 | 4770 | 249 | 0.9256 [0.9129, 0.9374]; brut 4415/4770 | 0.6105 [0.5158, 0.7053]; brut 58/95 |
| branching:13..16 | T0 | 69 | 6473 | 5830 | 643 | 0.5689 [0.5401, 0.5973]; brut 3316.5/5830 | 0.2029 [0.1159, 0.3043]; brut 14/69 |
| branching:13..16 | D1 | 69 | 6473 | 5830 | 643 | 0.6038 [0.5754, 0.6311]; brut 3520/5830 | 0.2029 [0.1159, 0.3043]; brut 14/69 |
| branching:13..16 | RF1 | 69 | 6473 | 5830 | 643 | 0.6443 [0.6117, 0.6755]; brut 3756/5830 | 0.2464 [0.1449, 0.3478]; brut 17/69 |
| branching:13..16 | T3-A | 69 | 6473 | 5830 | 643 | 0.6202 [0.5864, 0.6521]; brut 3616/5830 | 0.1594 [0.0725, 0.2464]; brut 11/69 |
| branching:13..16 | Jass1k | 69 | 6473 | 5830 | 643 | 0.7408 [0.7091, 0.7718]; brut 4319/5830 | 0.4783 [0.3623, 0.5942]; brut 33/69 |
| branching:13..16 | Jass5k | 69 | 6473 | 5830 | 643 | 0.7702 [0.7422, 0.7976]; brut 4490/5830 | 0.5362 [0.4203, 0.6522]; brut 37/69 |
| branching:13..16 | Jass50k | 69 | 6473 | 5830 | 643 | 0.7770 [0.7458, 0.8063]; brut 4530/5830 | 0.4783 [0.3623, 0.5942]; brut 33/69 |
| branching:13..16 | Jass200k | 69 | 6473 | 5830 | 643 | 0.7943 [0.7657, 0.8219]; brut 4631/5830 | 0.5072 [0.3913, 0.6232]; brut 35/69 |
| branching:13..16 | Jass1M | 69 | 6473 | 5830 | 643 | 0.8063 [0.7763, 0.8347]; brut 4700.5/5830 | 0.5507 [0.4348, 0.6667]; brut 38/69 |
| branching:13..16 | Scan1k | 69 | 6473 | 5830 | 643 | 0.8214 [0.7970, 0.8448]; brut 4788.5/5830 | 0.4348 [0.3188, 0.5507]; brut 30/69 |
| branching:13..16 | Scan5k | 69 | 6473 | 5830 | 643 | 0.8401 [0.8137, 0.8647]; brut 4898/5830 | 0.5217 [0.4058, 0.6377]; brut 36/69 |
| branching:13..16 | Scan50k | 69 | 6473 | 5830 | 643 | 0.8720 [0.8511, 0.8914]; brut 5084/5830 | 0.6377 [0.5217, 0.7536]; brut 44/69 |
| branching:13..16 | Scan200k | 69 | 6473 | 5830 | 643 | 0.8902 [0.8713, 0.9082]; brut 5190/5830 | 0.6522 [0.5362, 0.7681]; brut 45/69 |
| branching:13..16 | Scan1M | 69 | 6473 | 5830 | 643 | 0.9123 [0.8978, 0.9262]; brut 5318.5/5830 | 0.6957 [0.5797, 0.7971]; brut 48/69 |
| branching:13..16 | Scan2M | 69 | 6473 | 5830 | 643 | 0.9244 [0.9101, 0.9379]; brut 5389.5/5830 | 0.7536 [0.6522, 0.8551]; brut 52/69 |
| pieces:9..11 | T0 | 64 | 2041 | 1347 | 694 | 0.5471 [0.4889, 0.6023]; brut 737/1347 | 0.4688 [0.3438, 0.5938]; brut 30/64 |
| pieces:9..11 | D1 | 64 | 2041 | 1347 | 694 | 0.5501 [0.4920, 0.6066]; brut 741/1347 | 0.3750 [0.2656, 0.5000]; brut 24/64 |
| pieces:9..11 | RF1 | 64 | 2041 | 1347 | 694 | 0.6889 [0.6338, 0.7416]; brut 928/1347 | 0.4688 [0.3438, 0.5938]; brut 30/64 |
| pieces:9..11 | T3-A | 64 | 2041 | 1347 | 694 | 0.6221 [0.5455, 0.6888]; brut 838/1347 | 0.4688 [0.3438, 0.5938]; brut 30/64 |
| pieces:9..11 | Jass1k | 64 | 2041 | 1347 | 694 | 0.7610 [0.6981, 0.8163]; brut 1025/1347 | 0.6875 [0.5781, 0.7969]; brut 44/64 |
| pieces:9..11 | Jass5k | 64 | 2041 | 1347 | 694 | 0.7773 [0.7071, 0.8348]; brut 1047/1347 | 0.6250 [0.5000, 0.7344]; brut 40/64 |
| pieces:9..11 | Jass50k | 64 | 2041 | 1347 | 694 | 0.7732 [0.7121, 0.8312]; brut 1041.5/1347 | 0.6094 [0.4844, 0.7344]; brut 39/64 |
| pieces:9..11 | Jass200k | 64 | 2041 | 1347 | 694 | 0.7558 [0.6970, 0.8147]; brut 1018/1347 | 0.5938 [0.4688, 0.7188]; brut 38/64 |
| pieces:9..11 | Jass1M | 64 | 2041 | 1347 | 694 | 0.7684 [0.7119, 0.8233]; brut 1035/1347 | 0.6250 [0.5000, 0.7344]; brut 40/64 |
| pieces:9..11 | Scan1k | 64 | 2041 | 1347 | 694 | 0.8393 [0.7836, 0.8887]; brut 1130.5/1347 | 0.7969 [0.6875, 0.8906]; brut 51/64 |
| pieces:9..11 | Scan5k | 64 | 2041 | 1347 | 694 | 0.8255 [0.7531, 0.8892]; brut 1112/1347 | 0.7812 [0.6719, 0.8750]; brut 50/64 |
| pieces:9..11 | Scan50k | 64 | 2041 | 1347 | 694 | 0.8608 [0.8033, 0.9105]; brut 1159.5/1347 | 0.8281 [0.7344, 0.9219]; brut 53/64 |
| pieces:9..11 | Scan200k | 64 | 2041 | 1347 | 694 | 0.8953 [0.8518, 0.9331]; brut 1206/1347 | 0.8281 [0.7344, 0.9219]; brut 53/64 |
| pieces:9..11 | Scan1M | 64 | 2041 | 1347 | 694 | 0.9217 [0.8900, 0.9503]; brut 1241.5/1347 | 0.8906 [0.8125, 0.9531]; brut 57/64 |
| pieces:9..11 | Scan2M | 64 | 2041 | 1347 | 694 | 0.9302 [0.8982, 0.9570]; brut 1253/1347 | 0.9219 [0.8438, 0.9844]; brut 59/64 |
| pieces:12..15 | T0 | 30 | 838 | 765 | 73 | 0.5627 [0.4979, 0.6218]; brut 430.5/765 | 0.3333 [0.1667, 0.5000]; brut 10/30 |
| pieces:12..15 | D1 | 30 | 838 | 765 | 73 | 0.6157 [0.5679, 0.6638]; brut 471/765 | 0.3667 [0.2000, 0.5333]; brut 11/30 |
| pieces:12..15 | RF1 | 30 | 838 | 765 | 73 | 0.6993 [0.6348, 0.7579]; brut 535/765 | 0.4000 [0.2333, 0.5667]; brut 12/30 |
| pieces:12..15 | T3-A | 30 | 838 | 765 | 73 | 0.6706 [0.6093, 0.7237]; brut 513/765 | 0.3667 [0.2000, 0.5333]; brut 11/30 |
| pieces:12..15 | Jass1k | 30 | 838 | 765 | 73 | 0.7039 [0.6495, 0.7542]; brut 538.5/765 | 0.3667 [0.2000, 0.5333]; brut 11/30 |
| pieces:12..15 | Jass5k | 30 | 838 | 765 | 73 | 0.7248 [0.6911, 0.7648]; brut 554.5/765 | 0.4667 [0.3000, 0.6333]; brut 14/30 |
| pieces:12..15 | Jass50k | 30 | 838 | 765 | 73 | 0.7497 [0.7044, 0.7957]; brut 573.5/765 | 0.4333 [0.2667, 0.6000]; brut 13/30 |
| pieces:12..15 | Jass200k | 30 | 838 | 765 | 73 | 0.7791 [0.7229, 0.8345]; brut 596/765 | 0.4333 [0.2667, 0.6000]; brut 13/30 |
| pieces:12..15 | Jass1M | 30 | 838 | 765 | 73 | 0.7725 [0.7201, 0.8265]; brut 591/765 | 0.5333 [0.3667, 0.7000]; brut 16/30 |
| pieces:12..15 | Scan1k | 30 | 838 | 765 | 73 | 0.7562 [0.7026, 0.8075]; brut 578.5/765 | 0.4667 [0.3000, 0.6333]; brut 14/30 |
| pieces:12..15 | Scan5k | 30 | 838 | 765 | 73 | 0.7771 [0.7382, 0.8171]; brut 594.5/765 | 0.6333 [0.4667, 0.8000]; brut 19/30 |
| pieces:12..15 | Scan50k | 30 | 838 | 765 | 73 | 0.8379 [0.7845, 0.8851]; brut 641/765 | 0.6667 [0.5000, 0.8333]; brut 20/30 |
| pieces:12..15 | Scan200k | 30 | 838 | 765 | 73 | 0.8719 [0.8307, 0.9048]; brut 667/765 | 0.7000 [0.5333, 0.8667]; brut 21/30 |
| pieces:12..15 | Scan1M | 30 | 838 | 765 | 73 | 0.9196 [0.8983, 0.9374]; brut 703.5/765 | 0.8333 [0.7000, 0.9667]; brut 25/30 |
| pieces:12..15 | Scan2M | 30 | 838 | 765 | 73 | 0.9379 [0.9161, 0.9565]; brut 717.5/765 | 0.8000 [0.6333, 0.9333]; brut 24/30 |
| pieces:16..19 | T0 | 34 | 1602 | 1567 | 35 | 0.5798 [0.5320, 0.6195]; brut 908.5/1567 | 0.3529 [0.2059, 0.5294]; brut 12/34 |
| pieces:16..19 | D1 | 34 | 1602 | 1567 | 35 | 0.5456 [0.4970, 0.5916]; brut 855/1567 | 0.2059 [0.0882, 0.3529]; brut 7/34 |
| pieces:16..19 | RF1 | 34 | 1602 | 1567 | 35 | 0.5712 [0.5157, 0.6282]; brut 895/1567 | 0.1471 [0.0294, 0.2647]; brut 5/34 |
| pieces:16..19 | T3-A | 34 | 1602 | 1567 | 35 | 0.5948 [0.5216, 0.6652]; brut 932/1567 | 0.3824 [0.2353, 0.5588]; brut 13/34 |
| pieces:16..19 | Jass1k | 34 | 1602 | 1567 | 35 | 0.6726 [0.6197, 0.7306]; brut 1054/1567 | 0.4412 [0.2647, 0.6176]; brut 15/34 |
| pieces:16..19 | Jass5k | 34 | 1602 | 1567 | 35 | 0.7304 [0.6855, 0.7757]; brut 1144.5/1567 | 0.4412 [0.2647, 0.6176]; brut 15/34 |
| pieces:16..19 | Jass50k | 34 | 1602 | 1567 | 35 | 0.7138 [0.6533, 0.7738]; brut 1118.5/1567 | 0.4706 [0.2941, 0.6471]; brut 16/34 |
| pieces:16..19 | Jass200k | 34 | 1602 | 1567 | 35 | 0.7466 [0.6871, 0.8039]; brut 1170/1567 | 0.5588 [0.3824, 0.7353]; brut 19/34 |
| pieces:16..19 | Jass1M | 34 | 1602 | 1567 | 35 | 0.7613 [0.6964, 0.8230]; brut 1193/1567 | 0.5294 [0.3529, 0.7059]; brut 18/34 |
| pieces:16..19 | Scan1k | 34 | 1602 | 1567 | 35 | 0.7830 [0.7474, 0.8212]; brut 1227/1567 | 0.4412 [0.2647, 0.6176]; brut 15/34 |
| pieces:16..19 | Scan5k | 34 | 1602 | 1567 | 35 | 0.8101 [0.7797, 0.8439]; brut 1269.5/1567 | 0.5294 [0.3529, 0.7059]; brut 18/34 |
| pieces:16..19 | Scan50k | 34 | 1602 | 1567 | 35 | 0.8175 [0.7714, 0.8634]; brut 1281/1567 | 0.6471 [0.4706, 0.7941]; brut 22/34 |
| pieces:16..19 | Scan200k | 34 | 1602 | 1567 | 35 | 0.8494 [0.8144, 0.8868]; brut 1331/1567 | 0.6765 [0.5294, 0.8235]; brut 23/34 |
| pieces:16..19 | Scan1M | 34 | 1602 | 1567 | 35 | 0.8807 [0.8526, 0.9100]; brut 1380/1567 | 0.7059 [0.5588, 0.8529]; brut 24/34 |
| pieces:16..19 | Scan2M | 34 | 1602 | 1567 | 35 | 0.9110 [0.8806, 0.9396]; brut 1427.5/1567 | 0.8529 [0.7353, 0.9706]; brut 29/34 |
| pieces:20..24 | T0 | 32 | 2074 | 2044 | 30 | 0.5700 [0.5284, 0.6109]; brut 1165/2044 | 0.2500 [0.1250, 0.4062]; brut 8/32 |
| pieces:20..24 | D1 | 32 | 2074 | 2044 | 30 | 0.6360 [0.5987, 0.6704]; brut 1300/2044 | 0.1875 [0.0625, 0.3438]; brut 6/32 |
| pieces:20..24 | RF1 | 32 | 2074 | 2044 | 30 | 0.6644 [0.6199, 0.7041]; brut 1358/2044 | 0.2188 [0.0938, 0.3750]; brut 7/32 |
| pieces:20..24 | T3-A | 32 | 2074 | 2044 | 30 | 0.6517 [0.6095, 0.6918]; brut 1332/2044 | 0.2188 [0.0938, 0.3750]; brut 7/32 |
| pieces:20..24 | Jass1k | 32 | 2074 | 2044 | 30 | 0.7419 [0.7060, 0.7786]; brut 1516.5/2044 | 0.2188 [0.0938, 0.3750]; brut 7/32 |
| pieces:20..24 | Jass5k | 32 | 2074 | 2044 | 30 | 0.7534 [0.7166, 0.7915]; brut 1540/2044 | 0.3438 [0.1875, 0.5000]; brut 11/32 |
| pieces:20..24 | Jass50k | 32 | 2074 | 2044 | 30 | 0.7772 [0.7238, 0.8206]; brut 1588.5/2044 | 0.3125 [0.1562, 0.4688]; brut 10/32 |
| pieces:20..24 | Jass200k | 32 | 2074 | 2044 | 30 | 0.7948 [0.7490, 0.8385]; brut 1624.5/2044 | 0.5000 [0.3125, 0.6875]; brut 16/32 |
| pieces:20..24 | Jass1M | 32 | 2074 | 2044 | 30 | 0.8031 [0.7549, 0.8483]; brut 1641.5/2044 | 0.4062 [0.2500, 0.5938]; brut 13/32 |
| pieces:20..24 | Scan1k | 32 | 2074 | 2044 | 30 | 0.8068 [0.7691, 0.8449]; brut 1649/2044 | 0.2812 [0.1250, 0.4375]; brut 9/32 |
| pieces:20..24 | Scan5k | 32 | 2074 | 2044 | 30 | 0.8205 [0.7773, 0.8600]; brut 1677/2044 | 0.3125 [0.1562, 0.4688]; brut 10/32 |
| pieces:20..24 | Scan50k | 32 | 2074 | 2044 | 30 | 0.8518 [0.8260, 0.8761]; brut 1741/2044 | 0.5000 [0.3125, 0.6875]; brut 16/32 |
| pieces:20..24 | Scan200k | 32 | 2074 | 2044 | 30 | 0.8755 [0.8463, 0.9014]; brut 1789.5/2044 | 0.5625 [0.3750, 0.7188]; brut 18/32 |
| pieces:20..24 | Scan1M | 32 | 2074 | 2044 | 30 | 0.9048 [0.8892, 0.9211]; brut 1849.5/2044 | 0.5625 [0.3750, 0.7188]; brut 18/32 |
| pieces:20..24 | Scan2M | 32 | 2074 | 2044 | 30 | 0.9181 [0.8973, 0.9387]; brut 1876.5/2044 | 0.5938 [0.4062, 0.7500]; brut 19/32 |
| pieces:25..29 | T0 | 32 | 2195 | 2139 | 56 | 0.5147 [0.4711, 0.5601]; brut 1101/2139 | 0.1250 [0.0312, 0.2500]; brut 4/32 |
| pieces:25..29 | D1 | 32 | 2195 | 2139 | 56 | 0.6101 [0.5677, 0.6512]; brut 1305/2139 | 0.2188 [0.0938, 0.3750]; brut 7/32 |
| pieces:25..29 | RF1 | 32 | 2195 | 2139 | 56 | 0.6227 [0.5701, 0.6711]; brut 1332/2139 | 0.0938 [0.0000, 0.2188]; brut 3/32 |
| pieces:25..29 | T3-A | 32 | 2195 | 2139 | 56 | 0.6096 [0.5532, 0.6644]; brut 1304/2139 | 0.1562 [0.0312, 0.2812]; brut 5/32 |
| pieces:25..29 | Jass1k | 32 | 2195 | 2139 | 56 | 0.7302 [0.6751, 0.7839]; brut 1562/2139 | 0.3750 [0.2188, 0.5312]; brut 12/32 |
| pieces:25..29 | Jass5k | 32 | 2195 | 2139 | 56 | 0.7571 [0.7144, 0.8013]; brut 1619.5/2139 | 0.3125 [0.1562, 0.4688]; brut 10/32 |
| pieces:25..29 | Jass50k | 32 | 2195 | 2139 | 56 | 0.7924 [0.7586, 0.8264]; brut 1695/2139 | 0.3125 [0.1562, 0.4688]; brut 10/32 |
| pieces:25..29 | Jass200k | 32 | 2195 | 2139 | 56 | 0.8181 [0.7867, 0.8494]; brut 1750/2139 | 0.3125 [0.1562, 0.4688]; brut 10/32 |
| pieces:25..29 | Jass1M | 32 | 2195 | 2139 | 56 | 0.8310 [0.7931, 0.8673]; brut 1777.5/2139 | 0.4375 [0.2812, 0.5938]; brut 14/32 |
| pieces:25..29 | Scan1k | 32 | 2195 | 2139 | 56 | 0.8399 [0.8079, 0.8704]; brut 1796.5/2139 | 0.3438 [0.1875, 0.5000]; brut 11/32 |
| pieces:25..29 | Scan5k | 32 | 2195 | 2139 | 56 | 0.8576 [0.8318, 0.8828]; brut 1834.5/2139 | 0.5000 [0.3438, 0.6562]; brut 16/32 |
| pieces:25..29 | Scan50k | 32 | 2195 | 2139 | 56 | 0.8885 [0.8638, 0.9116]; brut 1900.5/2139 | 0.5000 [0.3125, 0.6562]; brut 16/32 |
| pieces:25..29 | Scan200k | 32 | 2195 | 2139 | 56 | 0.9051 [0.8815, 0.9272]; brut 1936/2139 | 0.5938 [0.4375, 0.7500]; brut 19/32 |
| pieces:25..29 | Scan1M | 32 | 2195 | 2139 | 56 | 0.9165 [0.8928, 0.9386]; brut 1960.5/2139 | 0.6250 [0.4688, 0.7812]; brut 20/32 |
| pieces:25..29 | Scan2M | 32 | 2195 | 2139 | 56 | 0.9355 [0.9198, 0.9487]; brut 2001/2139 | 0.5938 [0.4062, 0.7500]; brut 19/32 |
| pieces:30..34 | T0 | 38 | 2531 | 2427 | 104 | 0.5785 [0.5398, 0.6163]; brut 1404/2427 | 0.0789 [0.0000, 0.1842]; brut 3/38 |
| pieces:30..34 | D1 | 38 | 2531 | 2427 | 104 | 0.5999 [0.5589, 0.6376]; brut 1456/2427 | 0.2632 [0.1316, 0.4211]; brut 10/38 |
| pieces:30..34 | RF1 | 38 | 2531 | 2427 | 104 | 0.6218 [0.5815, 0.6589]; brut 1509/2427 | 0.2368 [0.1053, 0.3684]; brut 9/38 |
| pieces:30..34 | T3-A | 38 | 2531 | 2427 | 104 | 0.6032 [0.5663, 0.6371]; brut 1464/2427 | 0.1316 [0.0263, 0.2368]; brut 5/38 |
| pieces:30..34 | Jass1k | 38 | 2531 | 2427 | 104 | 0.7421 [0.7017, 0.7775]; brut 1801/2427 | 0.3947 [0.2368, 0.5526]; brut 15/38 |
| pieces:30..34 | Jass5k | 38 | 2531 | 2427 | 104 | 0.7783 [0.7417, 0.8120]; brut 1889/2427 | 0.3684 [0.2105, 0.5263]; brut 14/38 |
| pieces:30..34 | Jass50k | 38 | 2531 | 2427 | 104 | 0.7763 [0.7407, 0.8085]; brut 1884/2427 | 0.2895 [0.1579, 0.4474]; brut 11/38 |
| pieces:30..34 | Jass200k | 38 | 2531 | 2427 | 104 | 0.7932 [0.7565, 0.8262]; brut 1925/2427 | 0.2632 [0.1316, 0.4211]; brut 10/38 |
| pieces:30..34 | Jass1M | 38 | 2531 | 2427 | 104 | 0.8028 [0.7657, 0.8353]; brut 1948.5/2427 | 0.3684 [0.2105, 0.5263]; brut 14/38 |
| pieces:30..34 | Scan1k | 38 | 2531 | 2427 | 104 | 0.8416 [0.8128, 0.8667]; brut 2042.5/2427 | 0.3947 [0.2368, 0.5526]; brut 15/38 |
| pieces:30..34 | Scan5k | 38 | 2531 | 2427 | 104 | 0.8591 [0.8245, 0.8893]; brut 2085/2427 | 0.4737 [0.3158, 0.6316]; brut 18/38 |
| pieces:30..34 | Scan50k | 38 | 2531 | 2427 | 104 | 0.8842 [0.8613, 0.9035]; brut 2146/2427 | 0.5000 [0.3421, 0.6579]; brut 19/38 |
| pieces:30..34 | Scan200k | 38 | 2531 | 2427 | 104 | 0.8867 [0.8609, 0.9099]; brut 2152/2427 | 0.5000 [0.3421, 0.6579]; brut 19/38 |
| pieces:30..34 | Scan1M | 38 | 2531 | 2427 | 104 | 0.9194 [0.9017, 0.9354]; brut 2231.5/2427 | 0.4211 [0.2632, 0.5789]; brut 16/38 |
| pieces:30..34 | Scan2M | 38 | 2531 | 2427 | 104 | 0.9207 [0.8980, 0.9404]; brut 2234.5/2427 | 0.5263 [0.3684, 0.6842]; brut 20/38 |
| pieces:35..40 | T0 | 26 | 1304 | 1280 | 24 | 0.6508 [0.6005, 0.6995]; brut 833/1280 | 0.1538 [0.0385, 0.3077]; brut 4/26 |
| pieces:35..40 | D1 | 26 | 1304 | 1280 | 24 | 0.6328 [0.5645, 0.6918]; brut 810/1280 | 0.1538 [0.0385, 0.3077]; brut 4/26 |
| pieces:35..40 | RF1 | 26 | 1304 | 1280 | 24 | 0.7211 [0.6806, 0.7584]; brut 923/1280 | 0.2308 [0.0769, 0.3846]; brut 6/26 |
| pieces:35..40 | T3-A | 26 | 1304 | 1280 | 24 | 0.6750 [0.6339, 0.7157]; brut 864/1280 | 0.1538 [0.0385, 0.3077]; brut 4/26 |
| pieces:35..40 | Jass1k | 26 | 1304 | 1280 | 24 | 0.8293 [0.7937, 0.8620]; brut 1061.5/1280 | 0.6154 [0.4231, 0.8077]; brut 16/26 |
| pieces:35..40 | Jass5k | 26 | 1304 | 1280 | 24 | 0.8500 [0.8218, 0.8761]; brut 1088/1280 | 0.5385 [0.3462, 0.7308]; brut 14/26 |
| pieces:35..40 | Jass50k | 26 | 1304 | 1280 | 24 | 0.8523 [0.8185, 0.8835]; brut 1091/1280 | 0.4615 [0.2692, 0.6538]; brut 12/26 |
| pieces:35..40 | Jass200k | 26 | 1304 | 1280 | 24 | 0.8461 [0.8177, 0.8707]; brut 1083/1280 | 0.5385 [0.3462, 0.7308]; brut 14/26 |
| pieces:35..40 | Jass1M | 26 | 1304 | 1280 | 24 | 0.8520 [0.8241, 0.8767]; brut 1090.5/1280 | 0.4615 [0.2692, 0.6538]; brut 12/26 |
| pieces:35..40 | Scan1k | 26 | 1304 | 1280 | 24 | 0.8840 [0.8641, 0.9034]; brut 1131.5/1280 | 0.5385 [0.3462, 0.7308]; brut 14/26 |
| pieces:35..40 | Scan5k | 26 | 1304 | 1280 | 24 | 0.8930 [0.8709, 0.9139]; brut 1143/1280 | 0.6538 [0.4615, 0.8462]; brut 17/26 |
| pieces:35..40 | Scan50k | 26 | 1304 | 1280 | 24 | 0.9172 [0.8998, 0.9337]; brut 1174/1280 | 0.5769 [0.3846, 0.7692]; brut 15/26 |
| pieces:35..40 | Scan200k | 26 | 1304 | 1280 | 24 | 0.9281 [0.9118, 0.9433]; brut 1188/1280 | 0.6923 [0.5000, 0.8462]; brut 18/26 |
| pieces:35..40 | Scan1M | 26 | 1304 | 1280 | 24 | 0.9199 [0.8978, 0.9403]; brut 1177.5/1280 | 0.6154 [0.4231, 0.8077]; brut 16/26 |
| pieces:35..40 | Scan2M | 26 | 1304 | 1280 | 24 | 0.9391 [0.9216, 0.9555]; brut 1202/1280 | 0.7692 [0.6154, 0.9231]; brut 20/26 |

## Désaccords Jass / Scan

| Catégorie agrégée ULTRA256 | Compte | Taux |
|---|---:|---:|
| scan5m_vs_jass200k_top_choice_different | 147 | 0.5742 |
| t3_a_equals_jass200k_outside_scan5m_top_tie | 28 | 0.1094 |
| t3_a_in_scan5m_top_tie_jass200k_outside | 27 | 0.1055 |
| jass200k_in_scan5m_top_tie_t3_a_outside | 72 | 0.2812 |

Le JSON compagnon ventile aussi ces comptes/taux par phase, couleur, branching et pièces. Aucune FEN, identité sibling ou liste de position benchmark n'est publiée.

## Quarantaine

`SCAN_BENCHMARK_ONLY=true`. Le cohort et tous ses scores sont consommés et interdits pour tout training, tuning, feature/model selection, calibration, bake, force game ou promotion.
