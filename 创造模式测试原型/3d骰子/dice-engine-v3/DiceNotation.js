export class DiceNotation {
    constructor(notation) {
        const input = typeof notation === 'object' ? notation.notation : notation;
        this.set = [];
        this.setkeys = [];
        this.setid = 0;
        this.groups = [];
        this.totalDice = 0;
        this.op = '';
        this.constant = null;
        this.result = [];
        this.error = false;
        this.boost = 1;
        this.notation = '';
        this.vectors = [];
        if (!input || input === '0') {
            this.error = true;
        }
        this.parseNotation(input);
    }
    parseNotation(notation) {
        const cleaned = this.sanitize(notation);
        const op = this.notation.length > 0 ? '+' : '';
        this.notation += op + cleaned;
        const parts = cleaned.split('@'); // 0: dice notations, 1: forced results
        this.parseSets(parts[0]);
        this.parseForcedResults(parts[1]);
    }
    sanitize(notation) {
        if (!notation)
            return notation;
        const rage = notation.split('!').length - 1 || 0;
        if (rage > 0) {
            this.boost = Math.min(Math.max(rage, 0), 3) * 4;
        }
        const cleaned = notation.split('!').join('').split(' ').join('');
        const groupstarts = cleaned.split('(').length - 1;
        const groupends = cleaned.split(')').length - 1;
        if (groupstarts !== groupends)
            this.error = true;
        return cleaned;
    }
    parseSets(notationstring) {
        const rollregex = /(\+|\-|\*|\/|\%|\^|){0,1}()(\d*)([a-z]+\d+|[a-z]+|)(?:\{([a-z]+)(.*?|)\}|)()/i;
        // rollregex breakdown ("i" = case-insensitive):
        //   1: ([+\-*/%^]{0,1})         optional math operator for the group
        //   3: (\d*)                    number of dice
        //   4: ([a-z]+\d+|[a-z]+|)      the die type
        //   5/6: \{([a-z]+)(.*?|)\}     roll functions, e.g. "{r,2}" = reroll all 2s
        // predetermined results follow "@" (parsed separately), e.g. "@4,4,4"
        let remaining = notationstring;
        let runs = 0;
        const breaklimit = 30;
        let groupLevel = 0;
        let groupID = 0;
        while (!this.error && remaining.length > 0 && runs < breaklimit) {
            const res = rollregex.exec(remaining);
            if (res === null)
                break;
            runs += 1;
            remaining = remaining.substring(res[0].length);
            const next = this.consumeMatch(res, remaining.length === 0, runs, groupLevel, groupID);
            groupLevel = next.groupLevel;
            groupID = next.groupID;
        }
    }
    consumeMatch(res, isLast, runs, groupLevel, groupID) {
        const operator = res[1];
        const groupstart = res[2] && res[2].length > 0;
        let amount = res[3];
        let type = res[4];
        const funcname = res[5] || '';
        let funcargs = res[6] || '';
        const groupend = res[7] && res[7].length > 0;
        let addset = true;
        let level = groupLevel;
        let id = groupID;
        if (groupstart) {
            level += res[2].length;
        }
        funcargs = funcargs.split(',');
        if (!funcargs || funcargs.length < 1)
            funcargs = '';
        funcargs.shift();
        if (runs === 1 && isLast && !type && operator && amount) {
            type = 'd20';
            this.op = operator;
            this.constant = Number.parseInt(amount);
            amount = 1;
        }
        else if (runs > 1 && isLast && !type) {
            this.op = operator;
            this.constant = Number.parseInt(amount);
            addset = false;
        }
        if (addset) {
            this.addSet(amount, type, id, level, funcname, funcargs, operator);
        }
        if (groupend) {
            level -= res[7].length;
            id += res[7].length;
        }
        return { groupLevel: level, groupID: id };
    }
    parseForcedResults(forced) {
        if (this.error || !forced)
            return;
        const matched = forced.match(/-?\d+/g);
        if (matched !== null) {
            this.result.push(...matched);
        }
    }
    stringify(full = true) {
        if (this.set.length < 1)
            return '';
        let output = this.set
            .map((set, i) => this.formatSet(set, i))
            .join('');
        if (this.constant) {
            output += this.op + '' + Math.abs(this.constant);
        }
        if (full && this.result && this.result.length > 0) {
            output += '@' + this.result.join(',');
        }
        if (this.boost > 1) {
            output += '!'.repeat(this.boost / 4);
        }
        return output;
    }
    formatSet(set, index) {
        const op = index > 0 && set.op ? set.op : '';
        let output = op + set.num + set.type;
        if (set.func) {
            output += '{' + set.func + this.formatArgs(set.args) + '}';
        }
        return output;
    }
    formatArgs(args) {
        if (!args)
            return '';
        return ',' + (Array.isArray(args) ? args.join(',') : args);
    }
    addSet(amount, type, groupID = 0, groupLevel = 0, funcname = '', funcargs = '', operator = '+') {
        const count = Math.abs(Number.parseInt(amount || 1));
        const setkey = `${operator}${type}${groupID}${groupLevel}${funcname}${funcargs}`;
        const update = this.setkeys[setkey] != null;
        let setentry = {};
        if (update) {
            setentry = this.set[this.setkeys[setkey] - 1];
        }
        if (count > 0) {
            setentry.num = update ? count + setentry.num : count;
            setentry.type = type;
            setentry.sid = this.setid;
            setentry.gid = groupID;
            setentry.glvl = groupLevel;
            if (funcname)
                setentry.func = funcname;
            if (funcargs)
                setentry.args = funcargs;
            if (operator)
                setentry.op = operator;
            if (update) {
                this.set[this.setkeys[setkey] - 1] = setentry;
            }
            else {
                this.setkeys[setkey] = this.set.push(setentry);
            }
        }
        if (!update)
            ++this.setid;
    }
    static mergeNotation(prevNotation, newNotation) {
        if (!prevNotation)
            return newNotation;
        return {
            ...prevNotation,
            constant: prevNotation.constant + newNotation.constant,
            notation: prevNotation.notation + '+' + newNotation.notation,
            set: [...prevNotation.set, ...newNotation.set],
            totalDice: prevNotation.vectors.length + newNotation.vectors.length,
            vectors: [...prevNotation.vectors, ...newNotation.vectors],
        };
    }
}
