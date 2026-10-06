# Changelog

## [0.1.1](https://github.com/ozanozbeker/oxyscraper/compare/v0.1.0...v0.1.1) (2026-10-06)


### Bug Fixes

* pair an amazon URL batch's jobs and errors by URL ([#156](https://github.com/ozanozbeker/oxyscraper/issues/156)) ([4f45e85](https://github.com/ozanozbeker/oxyscraper/commit/4f45e8501e388bebf0b084d3d6a3066e574ae8e5))
* release each done job's results once the caller's loop has it ([#154](https://github.com/ozanozbeker/oxyscraper/issues/154)) ([2810e09](https://github.com/ozanozbeker/oxyscraper/commit/2810e099a0be2df13cf45487d958e0be5eca927b))

## [0.1.0](https://github.com/ozanozbeker/oxyscraper/compare/v0.0.1...v0.1.0) (2026-10-05)


### Features

* add Payload and the dry run ([#89](https://github.com/ozanozbeker/oxyscraper/issues/89)) ([7f5e23b](https://github.com/ozanozbeker/oxyscraper/commit/7f5e23bd244ab3a97a26abc4b02204eea59f70dd)), closes [#63](https://github.com/ozanozbeker/oxyscraper/issues/63)
* add the 32 grocery sources to the fake ([#130](https://github.com/ozanozbeker/oxyscraper/issues/130)) ([f9a79ee](https://github.com/ozanozbeker/oxyscraper/commit/f9a79ee279e1741cf12e634d6a7ff12745e31a16)), closes [#127](https://github.com/ozanozbeker/oxyscraper/issues/127)
* add the fake Oxylabs API ([#84](https://github.com/ozanozbeker/oxyscraper/issues/84)) ([f164aed](https://github.com/ozanozbeker/oxyscraper/commit/f164aedbd5a8222c3efc9806feba0bfba3220d47)), closes [#61](https://github.com/ozanozbeker/oxyscraper/issues/61)
* add the oxy run and oxy get commands ([#124](https://github.com/ozanozbeker/oxyscraper/issues/124)) ([09db22c](https://github.com/ozanozbeker/oxyscraper/commit/09db22cc5418526114dff66ab9e9b18bae4efefa)), closes [#76](https://github.com/ozanozbeker/oxyscraper/issues/76)
* add the six Amazon models ([#93](https://github.com/ozanozbeker/oxyscraper/issues/93)) ([61d8b53](https://github.com/ozanozbeker/oxyscraper/commit/61d8b537a6181be493501eae6c9b1c18391e8270)), closes [#65](https://github.com/ozanozbeker/oxyscraper/issues/65)
* add the universal model ([#97](https://github.com/ozanozbeker/oxyscraper/issues/97)) ([9e7a4f4](https://github.com/ozanozbeker/oxyscraper/commit/9e7a4f4075baa8c595d8866a4c33739e7b5c198d)), closes [#66](https://github.com/ozanozbeker/oxyscraper/issues/66)
* batch and pace submissions ([#117](https://github.com/ozanozbeker/oxyscraper/issues/117)) ([c952f69](https://github.com/ozanozbeker/oxyscraper/commit/c952f69204328f93e004d669ab2098ff6bfd61a9)), closes [#70](https://github.com/ozanozbeker/oxyscraper/issues/70)
* check Cloud Storage uploads ([#123](https://github.com/ozanozbeker/oxyscraper/issues/123)) ([d28076a](https://github.com/ozanozbeker/oxyscraper/commit/d28076aa7d924f5e44cdce15ad3b81c0f6d48fb5)), closes [#74](https://github.com/ozanozbeker/oxyscraper/issues/74)
* print the CLI's progress and messages to stderr ([#125](https://github.com/ozanozbeker/oxyscraper/issues/125)) ([7d41817](https://github.com/ozanozbeker/oxyscraper/commit/7d41817d95dc15e8503ffa56db247b537589a63f))
* record each source's job object in the fake ([#85](https://github.com/ozanozbeker/oxyscraper/issues/85)) ([d6102bf](https://github.com/ozanozbeker/oxyscraper/commit/d6102bf6f5ff9003acd7cf3913a06035e1cc7c59))
* report a run's progress and log its start, end and changes ([#116](https://github.com/ozanozbeker/oxyscraper/issues/116)) ([9a94528](https://github.com/ozanozbeker/oxyscraper/commit/9a94528dc7ffdac775801caa3c82d0e684cca929)), closes [#69](https://github.com/ozanozbeker/oxyscraper/issues/69)
* retry, reject and stop runs under the failure policy ([#101](https://github.com/ozanozbeker/oxyscraper/issues/101)) ([2c77a75](https://github.com/ozanozbeker/oxyscraper/commit/2c77a75585b006305f7859d796d8e10be4c0ea32))
* run jobs through Realtime ([#118](https://github.com/ozanozbeker/oxyscraper/issues/118)) ([1afc652](https://github.com/ozanozbeker/oxyscraper/commit/1afc6524dbec969fdfb4a374752f72cbe8dc09a9)), closes [#71](https://github.com/ozanozbeker/oxyscraper/issues/71)
* run payloads through Push-Pull ([#96](https://github.com/ozanozbeker/oxyscraper/issues/96)) ([0f599fc](https://github.com/ozanozbeker/oxyscraper/commit/0f599fcc65e19ffa35394b550e48abe18c0cc503)), closes [#67](https://github.com/ozanozbeker/oxyscraper/issues/67)
* stop at once on a second Ctrl+C ([#121](https://github.com/ozanozbeker/oxyscraper/issues/121)) ([5174f50](https://github.com/ozanozbeker/oxyscraper/commit/5174f50a227b5146529804d9464b3f5a548298e5)), closes [#75](https://github.com/ozanozbeker/oxyscraper/issues/75)
* type the instruction parameters ([#90](https://github.com/ozanozbeker/oxyscraper/issues/90)) ([c7a6b6a](https://github.com/ozanozbeker/oxyscraper/commit/c7a6b6a03e1679562bb3c9a49ea84128594c156d))
* write done jobs to a destination ([#119](https://github.com/ozanozbeker/oxyscraper/issues/119)) ([fd2e669](https://github.com/ozanozbeker/oxyscraper/commit/fd2e6693d674fcd94035f34c50a03fc0e1bbb36a)), closes [#72](https://github.com/ozanozbeker/oxyscraper/issues/72)
* write the run log ([#120](https://github.com/ozanozbeker/oxyscraper/issues/120)) ([5e2a767](https://github.com/ozanozbeker/oxyscraper/commit/5e2a7673b15ea356686636252f55d99a5265f745)), closes [#73](https://github.com/ozanozbeker/oxyscraper/issues/73)


### Bug Fixes

* bring tooling, comments and tests in step with the code ([#109](https://github.com/ozanozbeker/oxyscraper/issues/109)) ([eb7a0f3](https://github.com/ozanozbeker/oxyscraper/commit/eb7a0f39e208ee2edf4c95055017200947af668c)), closes [#106](https://github.com/ozanozbeker/oxyscraper/issues/106)
* count LLM payloads against the rendered limit ([#136](https://github.com/ozanozbeker/oxyscraper/issues/136)) ([7bec15d](https://github.com/ozanozbeker/oxyscraper/commit/7bec15d2409096b42efc82311a1100fc7f7660c7))
* keep a run going through any failure of one job ([#115](https://github.com/ozanozbeker/oxyscraper/issues/115)) ([a6c64c1](https://github.com/ozanozbeker/oxyscraper/commit/a6c64c1affdf934b1817d912c976a79c461706f2)), closes [#103](https://github.com/ozanozbeker/oxyscraper/issues/103)
* match the fake to the API before 0.1.0 ([#113](https://github.com/ozanozbeker/oxyscraper/issues/113)) ([315a1cc](https://github.com/ozanozbeker/oxyscraper/commit/315a1cc6dc3986ae38c4c1c4472ba7f639eeb4d1))
* read pages as the API does, and reject unknown context item keys ([#114](https://github.com/ozanozbeker/oxyscraper/issues/114)) ([562a453](https://github.com/ozanozbeker/oxyscraper/commit/562a4537fdc53037c0a99f2000fd5367d4650f9a)), closes [#104](https://github.com/ozanozbeker/oxyscraper/issues/104)
* read the rate-limit headers under their new names ([#133](https://github.com/ozanozbeker/oxyscraper/issues/133)) ([337b926](https://github.com/ozanozbeker/oxyscraper/commit/337b926136cf1acb1064c503ac311294e54ffdee))
* redact every credential in a storage_url ([#108](https://github.com/ozanozbeker/oxyscraper/issues/108)) ([e106192](https://github.com/ozanozbeker/oxyscraper/commit/e1061925cbd94cf8ab61e9133bc8d557e40719c2)), closes [#107](https://github.com/ozanozbeker/oxyscraper/issues/107)
* reject the keys a source does not take ([#100](https://github.com/ozanozbeker/oxyscraper/issues/100)) ([e52217e](https://github.com/ozanozbeker/oxyscraper/commit/e52217ef68b163c12809824307bb19ce25a28888)), closes [#99](https://github.com/ozanozbeker/oxyscraper/issues/99)
* return the API's field errors from the fake ([#98](https://github.com/ozanozbeker/oxyscraper/issues/98)) ([e593512](https://github.com/ozanozbeker/oxyscraper/commit/e5935127dfac9a64fa1f04da42f7a7e2c5be9122)), closes [#86](https://github.com/ozanozbeker/oxyscraper/issues/86)


### Documentation

* add live test findings comparing Realtime with Push-Pull ([#50](https://github.com/ozanozbeker/oxyscraper/issues/50)) ([0378fa8](https://github.com/ozanozbeker/oxyscraper/commit/0378fa8a3cc7551e79d38c2a2d60037c61ed9a33))
* add live test findings for parameters ([#36](https://github.com/ozanozbeker/oxyscraper/issues/36)) ([cf29c95](https://github.com/ozanozbeker/oxyscraper/commit/cf29c950d303ee3939c4096cb1e4669be70256e5))
* add live test findings on checking jobs at a run's rate ([#82](https://github.com/ozanozbeker/oxyscraper/issues/82)) ([d0af643](https://github.com/ozanozbeker/oxyscraper/commit/d0af6433d9b51dc0a8c207cc34b73ccfdd2cc62e)), closes [#59](https://github.com/ozanozbeker/oxyscraper/issues/59)
* add live test findings on jobs larger than a rate limit ([#55](https://github.com/ozanozbeker/oxyscraper/issues/55)) ([dc3dbd3](https://github.com/ozanozbeker/oxyscraper/commit/dc3dbd328b3407b0e98bc277c97613fe34fc2af0))
* add support's answers on rate limits ([#52](https://github.com/ozanozbeker/oxyscraper/issues/52)) ([d5ca42a](https://github.com/ozanozbeker/oxyscraper/commit/d5ca42a759e1e5ea562bee7c8ae7c9c49b294b4b))
* add the install commands and badges to the README ([#137](https://github.com/ozanozbeker/oxyscraper/issues/137)) ([caccb37](https://github.com/ozanozbeker/oxyscraper/commit/caccb37d44aa4cf110f10dbf75743b894c947e46))
* add the probe of the 32 sources the docs added ([#88](https://github.com/ozanozbeker/oxyscraper/issues/88)) ([3bc8b9a](https://github.com/ozanozbeker/oxyscraper/commit/3bc8b9a44ff8bebbdf63236bd41c2e350ee978dc))
* define a result as one page ([#37](https://github.com/ozanozbeker/oxyscraper/issues/37)) ([ff5a7cb](https://github.com/ozanozbeker/oxyscraper/commit/ff5a7cb66ea1ed65e0ab11d763b5c9ecea67a265))
* define Checkpoint, Faulted and Rejection, and add retention findings ([#42](https://github.com/ozanozbeker/oxyscraper/issues/42)) ([22bf2f3](https://github.com/ozanozbeker/oxyscraper/commit/22bf2f3afb8056a9aaed693b27081b498e787581))
* define Payload, Session and Run ([#39](https://github.com/ozanozbeker/oxyscraper/issues/39)) ([0756e6f](https://github.com/ozanozbeker/oxyscraper/commit/0756e6ff61a43e8a52eddbb85a0890b25e2c7490))
* define Run log in place of Checkpoint ([#51](https://github.com/ozanozbeker/oxyscraper/issues/51)) ([156ed8d](https://github.com/ozanozbeker/oxyscraper/commit/156ed8de26e5cd427d779233c1534dd1eacaf7f2))
* define Upload, Destination and Progress, and add Amazon and universal live test findings ([#49](https://github.com/ozanozbeker/oxyscraper/issues/49)) ([2c76cad](https://github.com/ozanozbeker/oxyscraper/commit/2c76cad574d25cb4587e956db63c0c23d15cb3a6))
* limit CONTRIBUTING.md to oxyscraper ([#95](https://github.com/ozanozbeker/oxyscraper/issues/95)) ([6b9ebf9](https://github.com/ozanozbeker/oxyscraper/commit/6b9ebf9148b0fe0f334ff248f33955287805f596))
* note where storage_url credentials stay in invalid-JSON errors ([#92](https://github.com/ozanozbeker/oxyscraper/issues/92)) ([0d5d5de](https://github.com/ozanozbeker/oxyscraper/commit/0d5d5de7347056edb63d9b8d7a58a96784783612))
* write the user guide ([#126](https://github.com/ozanozbeker/oxyscraper/issues/126)) ([e9008bf](https://github.com/ozanozbeker/oxyscraper/commit/e9008bfe1c6ab944c41ca070f43d24412b6d9ac6))


### Dependencies

* raise the httpx2 floor to 2.12.0 ([#102](https://github.com/ozanozbeker/oxyscraper/issues/102)) ([315fa1c](https://github.com/ozanozbeker/oxyscraper/commit/315fa1cca11445aefb66f5064192d87aab951175))
* raise the pydantic floor to 2.7.0 ([#91](https://github.com/ozanozbeker/oxyscraper/issues/91)) ([4a232ab](https://github.com/ozanozbeker/oxyscraper/commit/4a232abd96a1e040aa5eba540766e03f383656db))

## 0.0.1 (2026-09-28)


### Documentation

* add the release process and the docs site ([#33](https://github.com/ozanozbeker/oxyscraper/issues/33)) ([332c944](https://github.com/ozanozbeker/oxyscraper/commit/332c94405eff1f4e6f39c51adf8b471ec628b848))
* explain the day-to-day workflow ([#35](https://github.com/ozanozbeker/oxyscraper/issues/35)) ([bbb6325](https://github.com/ozanozbeker/oxyscraper/commit/bbb63257c16de7aba8f2ccc005487bd9ee20f484))
