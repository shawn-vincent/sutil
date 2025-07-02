#!/usr/bin/env node
// tags: #testtag

const yargs = require('yargs/yargs');
const { hideBin } = require('yargs/helpers');
const fs = require('fs');
const path = require('path');
const glob = require('glob');
const clipboardy = require('clipboardy');
const chalk = require('chalk');
const ignore = require('ignore');

/**
 * Checks if a file contains a specific tag.
 * The format expected is "tags: #tag1 #tag2"
 * @param {string} filePath - The path to the file.
 * @param {string} tag - The tag to search for.
 * @returns {boolean} - True if the tag is found, false otherwise.
 */
function fileHasTag(filePath, tag) {
    try {
        const fileContent = fs.readFileSync(filePath, 'utf8');
        // Use 's' flag for dotAll, so '.' matches newlines
        const tagRegex = new RegExp(`tags:.*#${tag}`, 's');
        return tagRegex.test(fileContent);
    } catch (e) {
        // Ignore errors for binary files or unreadable files
        return false;
    }
}

async function main() {
    let argv;
    try {
        argv = yargs(hideBin(process.argv))
            .scriptName('clop')
            .usage(`clop - A tool to aggregate file contents and copy them to the clipboard.
                
                    Usage: $0 [options] "[glob]"... +[tag]...`)
            .example('$0 "*.js" +frontend', 'Copy all .js files and files tagged with #frontend.')
            .example('$0 "*.ts" --not "*.test.ts"', 'Copy all TypeScript files except for test files.')
            .example('$0 "+backend" --not +legacy', 'Copy all files with #backend tag, excluding those with #legacy tag.')
            .option('not', {
                describe: 'Exclude files matching a glob pattern or tag. Can be used multiple times.',
                type: 'array',
                default: [],
            })
            .option('nogitignore', {
                describe: 'Ignore .gitignore files.  If omitted, .gitignore will be respected.',
                type: 'boolean',
                default: false,
            })
            .option('verbose', {
                describe: 'Show verbose error messages.',
                type: 'boolean',
                default: false,
            })
            .demandCommand(1, 'You must provide at least one glob pattern or tag.')
            .help()
            .alias('h', 'help')
            .epilogue(`Globs without '/' (eg. "*.txt") match files recursively.`)
            .epilogue(`./[glob] forces matches to current directory.`)
            .epilogue(`+[tag] matches files with a "tags: ... #[tag] ..." line.`)
            .epilogue("")
            .epilogue("`clop` is the sound of one hoof clipboarding.")
            .argv;
    } catch (err) {
        // Catch yargs parsing errors
        console.error(chalk.red('❌ Error parsing arguments:'));
        console.error(chalk.red(err.message));
        process.exit(1);
    }

    try {
        const { _, not: notPatterns, ignoreGitignore, verbose } = argv;

        const inclusionArgs = _.map(String);
        const exclusionArgs = (notPatterns || []).map(String);

        const inclusionGlobs = inclusionArgs.filter(p => !p.startsWith('+'));
        const inclusionTags = inclusionArgs.filter(p => p.startsWith('+')).map(t => t.substring(1));

        const exclusionGlobs = exclusionArgs.filter(p => !p.startsWith('+'));
        const exclusionTags = exclusionArgs.filter(p => p.startsWith('+')).map(t => t.substring(1));

        // --- .gitignore handling ---
        let ig = ignore();
        if (!ignoreGitignore) {
            const gitignorePath = path.join(process.cwd(), '.gitignore');
            if (fs.existsSync(gitignorePath)) {
                const gitignoreContent = fs.readFileSync(gitignorePath, 'utf8');
                ig.add(gitignoreContent);
            }
        }
        // Always ignore node_modules
        ig.add('node_modules');

        const allFiles = glob.sync('**/*', { nodir: true, dot: true });
        const accessibleFiles = allFiles.filter(file => !ig.ignores(path.relative(process.cwd(), file)));

        let matchedFiles = new Set();
        let unmatchedGlobs = new Set(inclusionGlobs);

        // --- Inclusion ---
        if (inclusionGlobs.length > 0) {
            inclusionGlobs.forEach(pattern => {
                let effectivePattern = pattern;
                if (!pattern.includes('/')) {
                    effectivePattern = `**/${pattern}`;
                }
                const found = glob.sync(effectivePattern, { ignore: '**/node_modules/**' });
                if (found.length > 0) {
                    unmatchedGlobs.delete(pattern);
                    found.forEach(file => matchedFiles.add(file));
                }
            });
        }

        if (inclusionTags.length > 0) {
            accessibleFiles.forEach(file => {
                for (const tag of inclusionTags) {
                    if (fileHasTag(file, tag)) {
                        matchedFiles.add(file);
                        break; 
                    }
                }
            });
        }

        let finalFiles = Array.from(matchedFiles);

        // --- Exclusion ---
        if (exclusionGlobs.length > 0) {
            const effectiveExclusionGlobs = exclusionGlobs.map(pattern => {
                if (!pattern.includes('/')) {
                    return `**/${pattern}`;
                }
                return pattern;
            });
            const exclusionSet = new Set(glob.sync(`{${effectiveExclusionGlobs.join(',')}}`, { ignore: '**/node_modules/**' }));
            finalFiles = finalFiles.filter(file => !exclusionSet.has(file));
        }

        if (exclusionTags.length > 0) {
            finalFiles = finalFiles.filter(file => {
                for (const tag of exclusionTags) {
                    if (fileHasTag(file, tag)) {
                        return false; // Exclude if any exclusion tag matches
                    }
                }
                return true;
            });
        }
        
        // --- Final Output ---
        if (unmatchedGlobs.size > 0) {
            console.log(chalk.yellow(`⚠️ The following patterns did not match any files: ${[...unmatchedGlobs].join(', ')}`));
        }

        if (finalFiles.length === 0) {
            console.log(chalk.yellow('⚠️ No files matched the given criteria.'));
            return;
        }

        let aggregatedContent = '';
        let totalBytes = 0;

        const formatBytes = (bytes) => {
            if (bytes === 0) return '0B';
            const k = 1024;
            const sizes = ['b', 'k', 'M', 'G', 'T'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + sizes[i];
        };

        for (const file of finalFiles) {
            const stats = fs.statSync(file);
            const fileSize = stats.size;
            totalBytes += fileSize;
            console.log(chalk.blue(`📄 ${file} (${formatBytes(fileSize)})`));
            const content = fs.readFileSync(file, 'utf8');
            aggregatedContent += `===== ${file} =====\n${content}\n\n`;
        }

        await clipboardy.write(aggregatedContent);
        console.log(chalk.green(`✅ Copied ${finalFiles.length} files to the clipboard (${formatBytes(totalBytes)})`));

    } catch (error) {
        console.error(chalk.red('❌ An unexpected error occurred:'));
        if (argv && argv.verbose) {
            console.error(error);
        } else {
            console.error(chalk.red(error.message));
        }
        process.exit(1);
    }
}

main();