import {conf} from "./buildConf.mjs";
import esbuild from "esbuild";

const ctx = await esbuild.context({
    ...conf
})

await ctx.watch()