<template>
    <div @scroll="handleScroll" style="height: 100vh; overflow-y: auto" ref="msgContainer">
        <div class="icoHi">
            <componentsHistory @getLiShi="getLiShi" @newAdd='newAdd'></componentsHistory>

        </div>
        <div class="top-text" v-if="dataText.length == 0">
            <h2> 你好，有问题尽管问！ </h2>

            <span class="top-state">仅限于<span class="top-state2">应用内的指标分析</span>哟</span>
        </div>

        <div v-show="dataText.length > 0" class="content" id="yourElementId" ref="container">

            <div v-for="(item, index) in dataText">
                <el-row>
                    <div class="my-content">
                        <span class="content-span"> {{ item.text }} </span>
                    </div>
                </el-row>
                <el-row>
                    <div style="position: relative;right: 10px;top: 3px;">
                        <img class="ml-2 " style="float: right;" :src="require('@/assets/images/wel/bianji.svg')" alt=""
                            @click='setText(item.text)'>
                        <img class="ml-2 " style="float: right;" :src="require('@/assets/images/wel/fuzhi.svg')" alt=""
                            @click='getText(item.text)' v-clipboard:copy="item.text" v-clipboard:success="onCopySuccess"
                            v-clipboard:error="onCopyError">
                    </div>
                </el-row>
                <el-row>
                    <div class="ai-content">
                        <!-- <span class="content-span" v-html="item.AItext"></span> -->
                        <span class="content-span">
                            <el-collapse value="99" @change="handleChange">

                                <el-collapse-item :name="item.activeNames">

                                    <template slot="title">
                                        <img style="width: 15px;height: 15px;"
                                            :src="require('@/assets/images/wel/huida.svg')" alt="">
                                        <span style="margin-left: 5px;font-size: 17px;font-weight: 600;"> 回答</span>
                                        <span class="ml-3 mr-1" style="font-size: 15px;">{{ item.reflectState ? '思考过程' :
                                            '终止思考' }} </span>
                                        <span style="color: #999;">
                                            <i class="el-icon-loading " v-if="item.reflectOnLog"></i>
                                            <span v-if="!item.reflectOnLog">{{ '(' + item.time + '秒)' }}</span>
                                        </span>
                                    </template>

                                    <div style="font-size: 12px;color: #999;">


                                        <el-steps direction="vertical" :active="item.active" finish-status="success"
                                            :key="item.active">

                                            <el-step title="问题识别与拆解" v-for="(list, listIndex) in item.activeArr"
                                                :key="listIndex">
                                                <template slot="icon">
                                                    <i class="el-icon-loading"></i>

                                                </template>
                                                <div slot="title" class="title-text">
                                                    {{ list.node }} <span class="ico-text">{{ list.timeJie }}</span>
                                                </div>
                                                <div slot="description" style="color: #585353;">
                                                    <span style="color: red;" v-show="list.node == '数据获取失败'">数据异常</span>
                                                    <div class="mt-3 mb-3"></div>

                                                    <!-- <Markdown ref="childRef" :key="index" content="已完成" /> -->
                                                </div>


                                            </el-step>
                                            <!-- <el-step title="问题识别与拆解" v-show="false">
                                                <template slot="icon">
                                                    <i class="el-icon-loading"></i>

                                                </template>
                                                <div slot="title" class="title-text">
                                                    问题识别与拆解 <span class="ico-text">{{ item.timeJie }}</span> </div>
                                                <div slot="description" style="color: #585353;">
                                                    <div class="mt-3 mb-3">{{ item.reflectOn2 }}</div>

                                                </div>


                                            </el-step> -->

                                            <!-- <el-step title="知识检索" v-show="false">
                                                <template slot="icon">
                                                    <i class="el-icon-loading"></i>
                                                </template>
                                                <div slot="title" class="title-text">
                                                    知识检索 <span class="ico-text">{{ item.timeJie2 }}</span> </div>
                                                <div slot="description" style="color: #585353;">
                                                    <div class="mt-3 mb-3">{{ item.reflectOn3 }}
                                                    </div>

                                                </div>
                                            </el-step> -->

                                            <!-- <el-step title="关键数据检索" v-show="false">
                                                <template slot="icon">
                                                    <i class="el-icon-loading"></i>
                                                </template>
                                                <div slot="title" class="title-text">
                                                    关键数据检索 <span class="ico-text">{{ item.timeJie3 }}</span></div>
                                                <div slot="description" style="color: #585353;">
                                                    <div class="mt-3 mb-3">{{ item.reflectOn4 }}</div>

                                                </div>
                                            </el-step> -->

                                            <!-- <el-step title="生成回答" v-show="false">
                                                <template slot="icon">
                                                    <i class="el-icon-loading"></i>
                                                </template>
                                                <div slot="title" class="title-text">
                                                    生成回答 <span class="ico-text">{{ item.timeJie4 }}</span></div>
                                                <div slot="description" style="color: #585353;">
                                                    <div class="mt-3 mb-3">{{ item.reflectOn4 }}</div>

                                                </div>
                                            </el-step> -->
                                        </el-steps>
                                    </div>
                                </el-collapse-item>

                            </el-collapse>
                            <Markdown ref="childRef" :key="index" :content="item.AItext" />

                        </span>
                    </div>

                </el-row>

                <div class="evaluate" v-if="item.isYou && !Interrupt"><!-- v-if="item.isYou && !Interrupt" -->
                    <img v-if="!isActivate" :src="require('@/assets/images/wel/zan.svg')" alt=""
                        @click='isShowPicture(1)'>
                    <img v-if="isActivate" :src="require('@/assets/images/wel/zan2.svg')" alt=""
                        @click='isShowPicture(2)'>
                    <i style="margin: 0px 5px;"></i>
                    <img v-if="!isLove" :src="require('@/assets/images/wel/noLove.svg')" alt=""
                        @click='isShowPicture(3, item)'>
                    <img v-if="isLove" :src="require('@/assets/images/wel/noLove2.svg')" alt=""
                        @click='isShowPicture(4)'>
                    <img class="ml-2" :src="require('@/assets/images/wel/new.svg')" alt=""
                        @click='getNewApi(item.text)'>



                </div>

            </div>

        </div>
        <div class="search-box" ref="myElement" :style="{ bottom: botVlu }">
            <template v-if="!shutoff && restaurants.length > 0 && input != ''">
                <div class="box-tishi">
                    <ul>
                        <li v-for="itemList in restaurants" @click="handleSelect(itemList.value)">{{ itemList.value }}
                        </li>

                    </ul>
                </div>
                <div>
                    <i class="el-icon-caret-bottom"></i>
                </div>
            </template>


            <div v-if="!shutoff" class="box">

                <div>
                    <!-- <span class="box-text">点这里,你可以开始提问了</span> -->
                    <el-input v-model="input" type="textarea" resize="none" placeholder="点这里,你可以开始提问了"
                        @keyup.enter.native="getSplitWordsAndPermission" @focus='incomingTrunk(false)'
                        @blur="incomingTrunk2(true)" @input="querySearch"></el-input>

                    <!-- <el-autocomplete @keyup.enter.native="getSplitWordsAndPermission" @focus='incomingTrunk(false)'
                        @blur="incomingTrunk2(true)" class="inline-input" v-model="input"
                        :fetch-suggestions="querySearch" placeholder="请输入内容" :trigger-on-focus="false" placement="top"
                        @select="handleSelect"></el-autocomplete> -->
                </div>
                <div class="box-bottom">
                    <div class="left">
                        <span v-for="(itemList, index) in btnArr" :class="isShow == index ? 'span-text' : 'span-text2'"
                            @click="ApiDepth(index, itemList)">{{ itemList.title }}</span>

                    </div>
                    <div class="right">
                        <!-- <img :src="require('@/assets/images/wel/yuyin.svg')" alt=""> -->

                        <!-- <i
                            style="width: 0.5px;height: 5px;border: 1px solid #c5c7ca;margin: 8px;position: relative;bottom: 6px;"></i> -->
                        <img :src="require('@/assets/images/wel/fas.svg')" alt="" @click="getSplitWordsAndPermission">


                        <!-- <div ></div> -->

                    </div>
                </div>
            </div>
            <div v-else style="margin-left: 45%;text-align: left;" class="mb-2">
                <span @click="stopApi">
                    <img style="position: relative;top: 4px;" :src="require('@/assets/images/wel/tingzhi.svg')" alt="">
                    <span style="color: #000;font-size: 17px; font-weight: 600;">
                        停止</span>
                </span>
            </div>
        </div>

        <van-popup v-model="showPopup" position="bottom" :style="{ height: '100%' }">
            <Feedback @close="showPopup = false" :row="row"></Feedback>
        </van-popup>




    </div>
</template>

<script>
// import TopTimeSelect from "@/components/tool/TopTimeSelect";
import componentsHistory from "./componentsHistory.vue";
import Feedback from "./feedback.vue";
import Markdown from './Markdown.vue';
import { splitWordsAndPermission, gethistory, questionKey, dataUuid, wordsChat } from "@/api/home/home.js";
import { postFormNoLoadAction6 } from "@/api/manage.js";
import { createdSession } from "@/api/home/home.js";
import { clearHttpRequestingList } from "@/utils/util.js";
import { Toast } from 'vant';
import { agentList } from "@/api/ai/ai.js";
const CHATBI_API_BASE = (process.env.VUE_APP_CHATBI_API_BASE || '/api/v1/chatbi').replace(/\/$/, '');
const CHATBI_COMPAT_BASE = (process.env.VUE_APP_CHATBI_COMPAT_BASE || '/gac/dify/ai').replace(/\/$/, '');
export default {

    inject: ["main"],
    components: { componentsHistory, Markdown, Feedback },
    data() {
        return {
            row: {},
            dataList: [
                {
                    text: '广汽传祺3月终端销量趋势分析'
                },
                {
                    text: '广汽集团终端销量分析'
                },
                {
                    text: '集团3月竞品分析'
                },
                {
                    text: '2024年第一季度财务报表'
                },
                {
                    text: '国际今年销量情况'
                },
            ],
            interval: '',
            interval2: '',
            interval3: '',
            input: '',
            showPopup: false,
            isShow: 0,
            isActivate: false,
            isLove: false,
            dataText: [],
            sessionId: '',
            agentId: '',
            streamData: '',
            streamController: {},
            loading: false,
            responseText: '',
            // markdownContent: '',
            Interrupt: false,//图片点赞状态
            shutoff: false,
            activeNames: '99',
            strResult: '',
            startTime: null,//开始计时
            controller: null,
            container: null,
            autoScroll: true,
            autoScrollEnabled: true,
            observer: null,
            textToCopy: '',
            scrollDebounce: null,
            sessionIdKey: '',
            agentIdKey: '',
            userInfo: JSON.parse(sessionStorage.getItem('userInfo')) || { UserId: '15205009333', name: 'zhou' },
            botVlu: '1.33333rem',
            restaurants: [],
            btnArr: [],
            markdownContent: "<think>问题: 埃安品牌2025年1月的销售情况\n\n### 执行结果:\n\n```sql\nSELECT brand_name AS `品牌`,\n yearmonth AS `年月`,\n ROUND(SUM(wholesale_qty),2) AS `批发销量`,\n ROUND(SUM(terminal_qty),2) AS `终端销量`\nFROM cockpit_plan_report_v3\nWHERE yearmonth = '202501'\n AND org_name = '广汽埃安'\n AND brand_name = 'エ安'\nGROUP BY brand_name, yearmonth;\n```\n\n| 品牌 | 年月 | 批发销量 | 终端销量 |\n|:-------|-------:|-----------:|------------:|\n| エ安 | 202501 | 6019.00 | 12664.00 |\n\n### 分析总结:\n从2025年1月销售数据显示：\n1. **渠道差异显著**：终端零售量（12,664台）是批发量（6,019台）的2.1倍；\n2. **去库存特征明显**：当月实际交付量为进货量的两倍以上；\n3. **市场表现强劲**：单月超12,600台的零售成绩显示出较强的市场消化能力；\n4. **渠道网络优势**：较高的零售转化率表明经销商体系具备良好的销售执行力。\n\n（注：因仅存</think>\n\n### 问题: 埃安品牌2025年1月的销售情况\n\n### 执行结果:\n\n```sql\nSELECT brand_name AS `品牌`,\n yearmonth AS `年月`,\n ROUND(SUM(wholesale_qty),2) AS `批发销量`,\n ROUND(SUM(terminal_qty),2) AS `终端销量`\nFROM cockpit_plan_report_v3\nWHERE yearmonth = '202501'\n AND org_name = '广汽埃安'\n AND brand_name = 'エ安'\nGROUP BY brand_name, yearmonth;\n```\n\n| 品牌 | 年月 | 批发销量 | 终端销量 |\n|:-------|-------:|-----------:|------------:|\n| エ安 | 202501 | 6019.00 | 12664.00 |\n\n### 分析总结:\n从2025年1月销售数据显示：\n1. **渠道差异显著**：终端零售量（12,664台）是批发量（6,019台）的2.1倍；\n2. **去库存特征明显**：当月实际交付量为进货量的两倍以上；\n3. **市场表现强劲**：单月超12,600台的零售成绩显示出较强的市场消化能力；\n4. **渠道网络优势**：较高的零售转化率表明经销商体系具备良好的销售执行力。\n\n（注：因仅存在单条记录未触发汇总计算）"
        }
    },

    watch: {

    },

    mounted() {
        this.getAgentId()
        this.handleEnter()
        this.container = document.getElementById('yourElementId');
        this.getLiShi()



        if (this.$route.query.value) { //点击热门话题进来
            this.input = this.$route.query.value
            this.getSplitWordsAndPermission()
        }
    },
    computed: {
        formattedResponse() {
            return this.responseText.replace(/\n/g, '<br>');
        },

    },
    methods: {

        lapili(index) {
            let clsName = ''
            if (index == 0) clsName = 'target'
            if (index == 1) clsName = 'target2'
            if (index == 2) clsName = 'target3'
            return clsName
        },
        ApiDepth(index, item) {
            this.isShow = index
            this.agentId = item.id
        },
        getSplitWordsAndPermission() {// 获取拆分后的单词和权限


            let obj = {
                "question": this.input,
                "sessionUuid": this.sessionIdKey,
                "userId": this.userInfo.UserId,
                "userName": this.userInfo.name,
                "answerMode": this.isShow == 1 ? "deep" : "quick",

            }
            if (this.input == '') return

            this.dataText.push({
                text: this.input,
                AItext: '',
                reflectOn: '', //思考文本
                reflectOn2: '', //思考文本2
                reflectOn3: '', //思考文本2
                reflectOn4: '', //思考文本2
                AItextLog: false, //AI文本
                active: 0,//步骤
                reflectOnLog: true, //思考圈圈
                time: 0,
                modelState: false,//模型状态
                reflectState: true,//思考状态
                timeJie: 0,
                timeJie2: 0,
                timeJie3: 0,
                timeJie4: 0,
                activeArr: [],
                activeNames: '99'
            })
            this.$nextTick(() => {
                setTimeout(() => {
                    this.dataText[this.dataText.length - 1].activeNames = '99' //默认展开
                }, 100);

            })
            this.shutoff = true
            this.Interrupt = true

            window.scrollTo(0, document.body.scrollHeight); //滚动到底部

            dataUuid(obj).then(res => {
                obj.id = res.data.id
                this.dataText[this.dataText.length - 1].id = res.data.id
                wordsChat(obj).then((res) => {

                })


                this.sendApi(res.data.id)


            })
            // splitWordsAndPermission(obj).then(res => {

            //     if (res.code == 200) {
            //         this.dataText[this.dataText.length - 1].id = res.data.id
            //         this.dataText[this.dataText.length - 1].reflectOn = res.msg
            //         this.dataText[this.dataText.length - 1].active = 1

            //         this.sendApi(res.data.id)
            //     } else {
            //         this.stopApi()
            //         this.dataText[this.dataText.length - 1].reflectOn = res.msg
            //     }
            // })




        },
        sendApi(id) {//发送功能

            this.startTime = performance.now();
            let obj = {
                "question": this.input,
                "sessionId": this.sessionId,
                "userId": this.userInfo.UserId,
                "userName": this.userInfo.name,
                "answerMode": this.isShow == 1 ? "deep" : "quick",
                'id': id,

            }

            let arr = ''
            // 取消之前的请求
            if (this.controller) {
                this.controller.abort();
            }

            this.controller = new AbortController();

            let strArr = []
            let strLength = []
            // window.scrollTo(0, document.body.scrollHeight); //滚动到底部
            this.$refs.msgContainer.scrollTop = this.$refs.msgContainer.scrollHeight;
            // postFormNoLoadAction6(
            //     `/gac/ragflow/ai/send-stream`,
            //     obj,
            //     async (res) => {

            //         const { code, msg } = JSON.parse(res.data)

            //         arr += msg

            //         let result = arr.split('<model>')[1];
            //         let result2 = arr.split('</know>')[1];
            //         let result3 = arr.split('<know>')[1];

            //         if (result) {

            //             if (result.indexOf('</model>') != -1) {
            //                 let str = '<model>' + result.split('</know>')[0]

            //                 const regex = /<model>(.*?)<\/model>/;
            //                 str = str.match(regex)[1];
            //                 this.dataText[this.dataText.length - 1].reflectOn2 = str
            //                 this.dataText[this.dataText.length - 1].active = 2



            //             }
            //         }
            //         if (result3) {
            //             if (result.indexOf('</know>') != -1) {

            //                 let str = result.split('</know>')[0]
            //                 str = str.split("<know>")[1]
            //                 console.log("cccccccccc", str)
            //                 // const regex = /<know>(.*?)<\/know>/;
            //                 // str = str.match(regex)[1];
            //                 this.dataText[this.dataText.length - 1].reflectOn3 = str
            //                 this.dataText[this.dataText.length - 1].active = 3



            //             }
            //         }
            //         if (result2) {
            //             const endTime = performance.now();
            //             // this.dataText[this.dataText.length - 1].time = ((endTime - this.startTime) / 1000).toFixed(2)

            //             this.dataText[this.dataText.length - 1].reflectOnLog = false
            //             this.dataText[this.dataText.length - 1].AItext = result2

            //         }

            //         if (arr.includes('</think>')) {//思考时间
            //             strArr.push({
            //                 time: performance.now()
            //             })

            //             this.dataText[this.dataText.length - 1].time = ((strArr[0].time - this.startTime) / 1000).toFixed(2)

            //         }
            //         if (code == '500') {
            //             this.dataText[this.dataText.length - 1].reflectOn = msg
            //         }
            //         setTimeout(() => {
            //             window.scrollTo(0, document.body.scrollHeight); //滚动到底部
            //         }, 1000);

            //     },
            //     { signal: this.controller.signal }, // 添加AbortSignal
            //     (okres) => {  //结束回调
            //         this.shutoff = false
            //         this.Interrupt = false
            //         console.log(arr, "okres");
            //     }
            // )

            let countdown = 300; // 设置倒计时时间，单位为秒
            // const intervalStop = setInterval(() => {
            //     // console.log(`剩余时间：${countdown}秒`);
            //     countdown--;

            //     if (countdown < 0) {
            //         clearInterval(intervalStop);
            //         this.dataText[this.dataText.length - 1].reflectOn4 = '当前使用人数较多，请重新加载页面后再次尝试'
            //         this.cancelRequest()
            //         this.stopApi()
            //         // console.log("倒计时结束");
            //     }
            // }, 1000);

            postFormNoLoadAction6(
                // `/gac/ragflow/ai/send-stream`,
                // `/gac/ragflow/ai/chat-messages`,
                CHATBI_API_BASE ? `${CHATBI_API_BASE}/messages/stream` : `${CHATBI_COMPAT_BASE}/chat-messages`,
                obj,
                async (res) => {

                    const streamEvent = this.normalizeChatBIStreamEvent(res)
                    if (!streamEvent) return
                    const { code, msg, data } = streamEvent
                    if (!data) return


                    if (data.type == 'message') {
                        arr += data.message
                    }
                    if (data.type == 'message_delta') {
                        arr += data.message || ''
                    }


                    // if (data.type == 'node_finished' && data.node == '问题识别与拆解') {

                    //     this.$nextTick(() => {
                    //         this.dataText[this.dataText.length - 1].active = 1
                    //         this.dataText[this.dataText.length - 1].timeJie = data.times
                    //     })

                    // }
                    // if (data.type == 'node_finished' && data.node == '知识检索') {
                    //     this.$nextTick(() => {
                    //         this.dataText[this.dataText.length - 1].active = 2
                    //         this.dataText[this.dataText.length - 1].timeJie2 = data.times
                    //     })

                    // }

                    // if (data.type == 'node_finished' && data.node == '关键数据检索') {
                    //     this.$nextTick(() => {
                    //         this.dataText[this.dataText.length - 1].active = 3
                    //         this.dataText[this.dataText.length - 1].timeJie3 = data.times
                    //     })

                    // }
                    // if (data.type == 'node_finished' && data.node == '生成回答') {
                    //     this.$nextTick(() => {
                    //         this.dataText[this.dataText.length - 1].active = 4
                    //         this.dataText[this.dataText.length - 1].timeJie4 = data.times
                    //     })

                    // }

                    if (data.type == 'node_started' && data.isShow == 1) {
                        this.dataText[this.dataText.length - 1].activeArr.push(data)
                    }
                    if (data.type == 'node_finished' && data.isShow == 1) {
                        strLength.push(data)
                        this.dataText[this.dataText.length - 1].active = strLength.length
                        console.log(strLength.length, "data");
                        this.dataText[this.dataText.length - 1].activeArr.forEach((item, index) => {
                            if (item.node == data.node) {
                                this.dataText[this.dataText.length - 1].activeArr[index].timeJie = data.times
                            }
                        })
                    }









                    let newStr = arr.replace(/<think>/g, '<details open><summary> 详情</summary><p>').replace(/<\/think>/g, '</p></details>');


                    this.dataText[this.dataText.length - 1].AItext = newStr

                    // document.querySelectorAll('details').forEach(details => {
                    //     details.removeAttribute('open'); //调完收起来
                    // });
                    // setTimeout(() => {

                    //     window.scrollTo(50, document.body.scrollHeight); //滚动到底部
                    // }, 500);

                    this.$nextTick(() => {
                        if (this.autoScroll) {
                            this.$refs.msgContainer.scrollTop = this.$refs.msgContainer.scrollHeight;
                        }
                    });
                },
                { signal: this.controller.signal }, // 添加AbortSignal
                (okres) => {  //结束回调
                    this.shutoff = false
                    this.Interrupt = false
                    this.dataText[this.dataText.length - 1].reflectOnLog = false
                    this.dataText[this.dataText.length - 1].time = ((performance.now() - this.startTime) / 1000).toFixed(2)


                    setTimeout(() => {
                        document.querySelectorAll('details').forEach(details => {
                            this.$nextTick(() => {
                                details.removeAttribute('open'); //调完收起来
                                if (details.innerHTML.length < 40) {
                                    details.remove()//删除没有详情的标签
                                }


                            })
                        });
                        this.dataText[this.dataText.length - 1].activeNames = this.dataText.length + 1
                    }, 50);

                    this.dataText[this.dataText.length - 1].activeArr.sort((a, b) => {
                        if (a.node === '生成完成') return 1;  // 将 '生成完成' 排在最后
                        if (b.node === '生成完成') return -1; // 其他元素保持原顺序
                        return 0;
                    });
                    // console.log("okres", this.dataText);
                }
            )
            // this.typeWriterReflectOn(this.reflectOnApi(this.markdownContent), this.dataText.length - 1, 40)
            // this.typeWriter(this.markdownContent, this.dataText.length - 1, 40)
            this.input = ''
            this.isActivate = false
            this.isLove = false
            // window.scrollTo(0, document.body.scrollHeight); //滚动到底部


            if (this.dataText) { //点赞
                this.dataText.forEach((item, index) => {
                    if (index == this.dataText.length - 1) {
                        item.isYou = true
                    } else {
                        item.isYou = false
                    }
                })
            }







        },
        normalizeChatBIStreamEvent(res) {
            const raw = res && res.data !== undefined ? res.data : res
            if (!raw) return null
            if (typeof raw === 'object') return raw
            const text = String(raw).trim()
            if (!text) return null
            const lines = text.split(/\r?\n/).map(item => item.trim()).filter(Boolean)
            for (let i = lines.length - 1; i >= 0; i--) {
                let line = lines[i]
                if (line.indexOf('data:') === 0) {
                    line = line.substring(5).trim()
                }
                if (!line || line === '[DONE]') continue
                try {
                    return JSON.parse(line)
                } catch (e) {
                    continue
                }
            }
            try {
                return JSON.parse(text)
            } catch (e) {
                console.warn('ChatBI stream parse skipped', text)
                return null
            }
        },

        scrollToBottom() {
            const container = this.$refs.container;
            container.scrollTop = container.scrollHeight;
            console.log('滚动到底部', container);
        },
        setupObserver() {
            this.observer = new IntersectionObserver((entries) => {
                // 当底部标记不可见时，说明用户手动滚动了
                this.autoScrollEnabled = entries[0].isIntersecting;
            }, {
                root: this.$refs.container,
                threshold: 0.1
            });

            this.observer.observe(this.$refs.bottomMarker);
        },
        typeWriter(text, elementId, speed) {
            let i = 0;
            const element = this.dataText[elementId].AItext
            const interval = setInterval(() => {
                if (i < text.length) {
                    this.dataText[elementId].AItext += text.charAt(i);
                    i++;
                } else {
                    console.log('完成输出');
                    this.dataText[elementId].AItextLog = true

                    this.shutoff = false
                    clearInterval(interval); // 完成输出后清除间隔
                }
            }, speed);
        },
        typeWriterReflectOn(text, elementId, speed, stop) { //思考输出

            let i = 0;
            const element = this.dataText[elementId].reflectOn
            this.interval = setInterval(() => {
                if (i < text.length) {
                    this.dataText[elementId].reflectOn += text.charAt(i);
                    i++;
                } else {
                    this.typeWriter(this.strResult, this.dataText.length - 1, 40)
                    this.dataText[this.dataText.length - 1].reflectOnLog = false
                    const endTime = performance.now();
                    this.dataText[this.dataText.length - 1].time = ((endTime - this.startTime) / 1000).toFixed(2)

                    clearInterval(this.interval); // 完成输出后清除间隔
                }
            }, speed);


        },
        typeWriter1(text, elementId, speed, text2, text3) {
            let i = 0;

            const interval = setInterval(() => {
                if (i < text.length) {
                    this.dataText[elementId].reflectOn2 += text.charAt(i);
                    i++;
                } else {


                    // this.dataText[elementId].active = 2
                    this.typeWriter2(text2, this.dataText.length - 1, 40, text3)

                    window.scrollTo(0, document.body.scrollHeight); //滚动到底部

                    clearInterval(interval); // 完成输出后清除间隔
                }
            }, speed);
        },
        typeWriter2(text, elementId, speed, text3) {
            let i = 0;

            this.interval2 = setInterval(() => {
                if (i < text.length) {
                    this.dataText[elementId].reflectOn3 += text.charAt(i);
                    i++;
                } else {


                    // this.dataText[elementId].active = 3
                    this.typeWriter3(text3, this.dataText.length - 1, 20)

                    clearInterval(this.interval2); // 完成输出后清除间隔
                }
            }, speed);
        },
        typeWriter3(text, elementId, speed) {
            let i = 0;

            this.interval3 = setInterval(() => {
                if (i < text.length) {
                    this.dataText[elementId].AItext += text.charAt(i);
                    setTimeout(() => {
                        window.scrollTo(0, document.body.scrollHeight); //滚动到底部
                    }, 1000);
                    i++;
                } else {


                    this.dataText[elementId].reflectOnLog = false
                    this.shutoff = false
                    this.Interrupt = false

                    clearInterval(this.interval3); // 完成输出后清除间隔
                }
            }, speed);
        },
        reflectOnApi(strValue) { //截取思考中的字符串
            let htmlString = strValue;
            let startTag = '<think>';
            let endTag = '</think>';
            let startIndex = htmlString.indexOf(startTag) + startTag.length;
            let endIndex = htmlString.indexOf(endTag);
            let content = htmlString.substring(startIndex, endIndex); // "你好呀"
            return content
        },
        isShowPicture(val, item) {

            if (val == 1) {
                this.isActivate = true
                this.isLove = false
            } else if (val == 2) {
                this.isActivate = false
            } else if (val == 3) {
                this.isLove = true
                this.isActivate = false
                this.showPopup = true
                this.row = item
            } else if (val == 4) {
                this.isLove = false
            }
        },
        handleChange(val) {
            console.log(val);

        },
        handleEnter() {

            this.sessionId = this.$route.query.sessionId
            // this.agentId = this.$route.query.agentId
            this.sessionIdKey = this.$route.query.sessionIdKey || this.$route.query.sessionUuid
            this.agentIdKey = this.$route.query.agentIdKey


        },
        async handleSubmit() {
            if (this.loading) {
                this.cancelRequest();
                return;
            }

            if (!this.userInput.trim()) return;

            this.loading = true;
            this.responseText = '';

            // 使用封装的流式请求方法
            const { promise, cancel } = postStreamAction('/ai-stream', {
                prompt: this.userInput
            }, {
                onMessage: (data) => {
                    this.responseText += data.choices?.[0]?.delta?.content || '';
                    this.$nextTick(() => {
                        this.$refs.responseArea.scrollTop = this.$refs.responseArea.scrollHeight;
                    });
                },
                onDone: () => {
                    this.loading = false;
                },
                onError: (error) => {
                    this.responseText += `\n请求失败: ${error.message}`;
                    this.loading = false;
                }
            });

            this.streamController = { cancel };
            await promise;
        },
        getNewApi(textValue) {
            this.input = textValue
            this.getSplitWordsAndPermission()
        },

        async getText(item) {//复制文本
            // this.textToCopy = item
            // try {
            //     if (navigator.clipboard) {
            //         await navigator.clipboard.writeText(this.textToCopy)
            //     } else {
            //         this.fallbackCopyText()
            //     }
            //     this.showToast('复制成功')
            // } catch (err) {
            //     console.error('复制失败:', err)
            //     this.showToast('复制失败，请手动复制')
            // }
        },
        onCopySuccess(val) {

            this.$copyText(val.text.trim()).then(() => {
                this.showToast('复制成功')

            });
        },
        onCopyError() { },
        fallbackCopyText() {
            const textarea = document.createElement('textarea')
            textarea.value = this.textToCopy
            textarea.style.position = 'fixed'
            document.body.appendChild(textarea)
            textarea.select()

            try {
                document.execCommand('copy')
            } finally {
                document.body.removeChild(textarea)
            }
        },

        handleScroll() {

            const container = this.$refs.msgContainer;
            // 判断用户是否手动向上滑动（当前滚动位置距离底部超过一定阈值）
            const threshold = 50;
            this.autoScroll = container.scrollHeight - container.scrollTop - container.clientHeight <= threshold;
        },
        showToast(message) {
            // 使用你喜欢的提示方式，如vant、mint-ui的toast或自定义实现
            Toast.success(message);
        },
        setText(item) {//编辑文本
            this.input = item
        },
        cancelRequest() { //终止请求
            if (this.controller) {
                this.controller.abort();
                this.controller = null;
            }
        },
        stopApi() {
            this.shutoff = false
            this.dataText[this.dataText.length - 1].reflectOnLog = false
            this.dataText[this.dataText.length - 1].reflectState = false
            if (!this.dataText[this.dataText.length - 1].reflectOn2) {
                this.dataText[this.dataText.length - 1].modelState = true
            }

            this.input = ''
            clearInterval(this.interval);
            clearInterval(this.interval2);
            clearInterval(this.interval3);
            this.cancelRequest()
            clearHttpRequestingList() //数据校验停止

            console.log('停止',);
        },
        getLiShi(item) {  //获取历史记录
            let urlId = this.$route.query.sessionUuid


            if (item) {
                let obj = {
                    sessionUuid: item,
                    userId: this.userInfo.UserId,
                }
                gethistory(obj).then(res => {
                    this.dataText = []
                    let dataArray = res.data

                    dataArray.forEach((item, index) => {
                        let next = 0
                        let newStr = ''
                        let arr = ''
                        let reflectOn2 = ''
                        let reflectOn3 = ''
                        let reflectOn4 = ''
                        let timeJie = 0
                        let timeJie2 = 0
                        let timeJie3 = 0
                        let timeJie4 = 0
                        let activeArr = []
                        let strLength = []
                        if (item.answer) {
                            const data = JSON.parse(item.answer)
                            data.forEach((list) => {
                                if (list.type == 'message') {
                                    arr += list.message
                                }

                                // if (list.type == 'node_finished' && list.node == '问题识别与拆解') {

                                //     this.$nextTick(() => {
                                //         next = 1
                                //         timeJie = list.times
                                //     })

                                // }
                                // if (list.type == 'node_finished' && list.node == '知识检索') {
                                //     this.$nextTick(() => {
                                //         next = 2
                                //         timeJie2 = list.times
                                //     })

                                // }

                                // if (list.type == 'node_finished' && list.node == '关键数据检索') {
                                //     this.$nextTick(() => {
                                //         next = 3
                                //         timeJie3 = list.times
                                //     })

                                // }
                                // if (list.type == 'node_finished' && list.node == '生成回答') {
                                //     this.$nextTick(() => {
                                //         next = 4
                                //         timeJie4 = list.times
                                //     })

                                // }



                                if (list.type == 'node_started' && list.isShow == 1) {
                                    activeArr.push(list)
                                }
                                if (list.type == 'node_finished' && list.isShow == 1) {
                                    strLength.push(list)
                                    next = strLength.length

                                    activeArr.forEach((item, index) => {
                                        if (item.node == list.node) {
                                            activeArr[index].timeJie = list.times
                                        }
                                    })
                                }

                            })


                            activeArr.sort((a, b) => {
                                if (a.node === '生成完成') return 1;  // 将 '生成完成' 排在最后
                                if (b.node === '生成完成') return -1; // 其他元素保持原顺序
                                return 0;
                            });
                            newStr = arr.replace(/<think>/g, '<details ><summary>详情 </summary><p>').replace(/<\/think>/g, '</p></details>');


                        }



                        this.$nextTick(() => {
                            this.dataText.push({
                                text: item.question,
                                AItext: newStr, //正文输出
                                reflectOn: '', //思考文本
                                AItextLog: false, //AI文本
                                reflectOn2: reflectOn2, //思考文本2
                                reflectOn3: reflectOn3, //思考文本2
                                reflectOn4: reflectOn4, //思考文本2
                                reflectOnLog: false, //思考圈圈
                                time: item.answerTime || 0,
                                active: next,//步骤
                                reflectState: true,//思考状态
                                timeJie: timeJie,
                                timeJie2: timeJie2,
                                timeJie3: timeJie3,
                                timeJie4: timeJie4,
                                isYou: true,
                                activeArr: activeArr,
                                id: item.id,
                            })
                            this.$nextTick(() => {
                                document.querySelectorAll('details').forEach(details => {
                                    if (details.innerHTML.length < 40) {
                                        details.remove()//删除没有详情的标签
                                    }
                                });
                            })

                        })
                        this.Interrupt = false

                    })


                })
                console.log('历史记录11111', item);

            } else if (urlId) {
                console.log('历史记录2', urlId);
                let obj = {
                    sessionUuid: urlId,
                    userId: this.userInfo.UserId,
                }
                gethistory(obj).then(res => {

                    this.dataText = []
                    let dataArray = res.data

                    dataArray.forEach((item, index) => {
                        let next = 0
                        let newStr = ''
                        let arr = ''
                        let reflectOn2 = ''
                        let reflectOn3 = ''
                        let reflectOn4 = ''
                        let timeJie = 0
                        let timeJie2 = 0
                        let timeJie3 = 0
                        let timeJie4 = 0
                        let activeArr = []
                        let strLength = []
                        if (item.answer) {
                            const data = JSON.parse(item.answer)
                            data.forEach((list) => {
                                if (list.type == 'message') {
                                    arr += list.message
                                }

                                // if (list.type == 'node_finished' && list.node == '问题识别与拆解') {

                                //     this.$nextTick(() => {
                                //         next = 1
                                //         timeJie = list.times
                                //     })

                                // }
                                // if (list.type == 'node_finished' && list.node == '知识检索') {
                                //     this.$nextTick(() => {
                                //         next = 2
                                //         timeJie2 = list.times
                                //     })

                                // }

                                // if (list.type == 'node_finished' && list.node == '关键数据检索') {
                                //     this.$nextTick(() => {
                                //         next = 3
                                //         timeJie3 = list.times
                                //     })

                                // }
                                // if (list.type == 'node_finished' && list.node == '生成回答') {
                                //     this.$nextTick(() => {
                                //         next = 4
                                //         timeJie4 = list.times
                                //     })

                                // }
                                if (data.type == 'node_started' && data.node == '答复数据口径') {
                                    arr += `!!!`
                                    console.log("答复数据口径", data)
                                }



                                if (list.type == 'node_started' && list.isShow == 1) {
                                    activeArr.push(list)
                                }
                                if (list.type == 'node_finished' && list.isShow == 1) {
                                    strLength.push(list)
                                    next = strLength.length

                                    activeArr.forEach((item, index) => {
                                        if (item.node == list.node) {

                                            activeArr[index].timeJie = list.times
                                        }
                                    })
                                }

                            })
                            activeArr.sort((a, b) => {
                                if (a.node === '生成完成') return 1;  // 将 '生成完成' 排在最后
                                if (b.node === '生成完成') return -1; // 其他元素保持原顺序
                                return 0;
                            });
                            arr = arr.replace(/数据口径说明\n\n/g, '<span class="itemStrShu">数据口径说明<br><br>').replace(/!!!/g, '</sapn>\n\n');

                            newStr = arr.replace(/<think>/g, '<details ><summary>详情 </summary><p>').replace(/<\/think>/g, '</p></details>');


                        }



                        this.$nextTick(() => {
                            this.dataText.push({
                                text: item.question,
                                AItext: newStr, //正文输出
                                reflectOn: '', //思考文本
                                AItextLog: false, //AI文本
                                reflectOn2: reflectOn2, //思考文本2
                                reflectOn3: reflectOn3, //思考文本2
                                reflectOn4: reflectOn4, //思考文本2
                                reflectOnLog: false, //思考圈圈
                                time: item.answerTime || 0,
                                active: next,//步骤
                                reflectState: true,//思考状态
                                timeJie: timeJie,
                                timeJie2: timeJie2,
                                timeJie3: timeJie3,
                                timeJie4: timeJie4,
                                isYou: true,
                                activeArr: activeArr,
                                id: item.id,
                            })
                            this.$nextTick(() => {
                                document.querySelectorAll('details').forEach(details => {
                                    if (details.innerHTML.length < 40) {
                                        details.remove()//删除没有详情的标签
                                    }
                                });
                            })
                        })
                        this.Interrupt = false

                    })


                })



            }
        },
        incomingTrunk(val) {

            this.botVlu = '5px'
            this.$bus.emit('message', val)
        },
        incomingTrunk2(val) {
            setTimeout(() => {

                this.botVlu = '1.33333rem'
                this.$bus.emit('message', val)
            }, 100);

        },
        newAdd() {
            this.dataText = []
            this.shutoff = false
            this.input = ''
            createdSession({}).then(res => {
                this.sessionIdKey = res.data.id
            })
            this.cancelRequest()
            clearHttpRequestingList() //数据校验停止
            console.log('newAdd');
        },
        handleSelect(item) {
            this.input = item
            this.getSplitWordsAndPermission()
            console.log(item, "555555555555");
        },
        querySearch(queryString, cb) {
            console.log('querySearch', queryString);

            questionKey({ question: queryString }).then(res => {
                if (res.code == 200) {
                    res.data.forEach(item => {
                        item.value = item.question
                        item.address = item.question
                    })
                    this.restaurants = res.data
                    // var restaurants = this.restaurants;
                    // var results = queryString ? restaurants.filter(this.createFilter(queryString)) : restaurants;
                    // 调用 callback 返回建议列表的数据
                    // cb(results);
                }

            })


        },
        createFilter(queryString) {
            return (restaurant) => {
                return (restaurant.value.toLowerCase().indexOf(queryString.toLowerCase()) === 0);
            };
        },
        getAgentId() {
            agentList().then((res) => {
                this.btnArr = res.data
                this.agentId = res.data[0].id
            })
        },
    },
    beforeDestroy() {
        console.log('销毁');
        this.cancelRequest();

    }
}
</script>

<style scoped lang="less">
.icoHi {
    position: fixed;
    top: 0px;
    z-index: 999;
    background: #fff;
    width: 100%;

}

.top-text {
    margin-top: 24vh;
    text-align: center;

    h2 {
        margin-bottom: 5px;
        font-weight: 500;
    }

    .top-state {
        font-size: 14px;

        .top-state2 {
            color: #0881fa;
        }
    }
}

.content {
    margin-top: 60px;
    margin-bottom: 180px;

    // height: 560px;
    // overflow-y: auto;
    // border: 1px solid #eee;
    // padding: 10px;
    // scroll-behavior: smooth;
    /* 平滑滚动 */
}

.my-content {



    .content-span {
        font-size: 15px;
        float: right;
        max-width: 80%;
        background: #2563EB;
        color: #fff;
        padding: 8px;
        border-radius: 10px;
        // text-align: center;

        margin-left: auto;
        margin-right: 10px;
        margin-top: 10px;



    }




}

.ai-content {
    .content-span {
        font-size: 13px;
        float: left;
        max-width: 85%;
        background: #f7fafc;
        color: #585353;
        padding: 15px;
        border-radius: 10px;
        margin-right: auto;
        margin-left: 10px;
        margin-top: 10px;
        width: 85%;
        h1 {
            font-size: 18px;
        }

        /deep/ .el-collapse-item__header {
            background-color: #f7fafc;
        }

        /deep/ .el-collapse-item__wrap {
            background-color: #f7fafc;
        }

        /deep/ .el-collapse {
            border-top: 0px;
        }

        /deep/ .el-step__icon {
            width: 0.51333rem;
            height: 0.51333rem
        }

        .bor-cor {
            /deep/ .el-step__icon {
                border-color: red;
            }
        }

        /deep/ .el-icon-close {
            color: red;

        }

        /deep/ .el-step__line {
            top: 5px;
            left: 9px;
            // margin-top: 20px;
            bottom: -4px;
        }


    }

    .title-text {
        font-size: 15px;
        color: #585353;
        font-weight: 600;

        .ico-text {
            font-size: 13px;
            color: #a0a6ad;
            font-weight: 300;
        }
    }

}

.evaluate {
    margin-top: 10px;
    margin-left: 20px;


}

.box {
    margin-left: auto;
    margin-right: auto;
    width: 95%;
    height: 100px;
    border-radius: 10px;
    position: relative;

    &::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        border-radius: 5px;
        /* 继承父元素的圆角 */
        padding: 1px;
        /* 边框宽度 */
        box-sizing: border-box;
        /* 使 padding 不影响实际大小 */
        background: linear-gradient(45deg, #5ecbff, #5a78ff, #64f4ff, #86efac);
        /* 渐变色 */
        -webkit-mask: linear-gradient(#84bdf3 0 0) content-box, linear-gradient(#82e7b1 0 0);
        /* 遮罩 */
        -webkit-mask-composite: destination-out;
        /* 将两个渐变叠加 */
        mask-composite: exclude;
        /* 将两个渐变叠加 */
    }

    .box-text {
        display: block;
        color: #999;
        font-size: 12px;
        padding-left: 10px;
        padding-top: 10px;
    }

    .box-bottom {
        padding: 0px 10px;
        position: absolute;
        bottom: 0px;
        display: flex;
        width: 100%;

        .left {
            width: 70%;
            // flex: 1;

            span {
                background: #eff6ff;
                font-size: 13px;
                position: relative;
                // top: 0.1223rem;
                padding: 4px;
                margin-right: 10px;
                border-radius: 5px;
                width: 90px;
                display: block;
                float: left;
                text-align: center;
            }

            .span-text {
                color: #0881fa;
                border: 1px solid #0881fa;
            }

            .span-text2 {
                color: #767b7e;
            }
        }

        .right {
            flex: 1;
            text-align: right;

            img {
                width: 28px;
                height: 28px;

            }
        }
    }

    padding-bottom: 5px;

    /deep/ .el-textarea__inner {
        width: 98%;
        margin-top: 2px;
        margin-left: 2px;
        max-height: 50px;
        border: 0px;
        font-size: 13px;
        min-height: 60px !important;
    }


}



.search-box {
    position: fixed;

    // bottom: 50px;
    width: 100%;
    text-align: center;
    margin-left: auto;
    margin-right: auto;
    z-index: 99;
    background: #fff;
    padding-bottom: env(safe-area-inset-bottom);

    /deep/ .el-input__inner {
        z-index: 99;
        border: none;
        width: 98%;
        margin: 2px;

    }

    .btn {
        background-color: #fff;
        border: none;
        color: #1c6bf4;
    }

    .box-tishi {
        width: 9.24667rem;
        // height: 50px;
        margin-left: 10px;
        margin-right: auto;
        padding: 10px;
        border-radius: 5px;
        border: 1px solid rgb(228, 231, 237);



        li {
            color: #606266;
            margin-bottom: 8px;
        }
    }



    .el-icon-caret-bottom {
        position: relative;
        top: -9px;
        margin-left: 20px;
        color: #dce1e1;
        font-size: 25px;
    }
}
</style>
