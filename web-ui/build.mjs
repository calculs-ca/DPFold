
import esbuild from 'esbuild';
import {conf} from "./buildConf.mjs";

esbuild.build({
    ...conf,
    minify: true
})