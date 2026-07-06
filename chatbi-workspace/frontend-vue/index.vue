<template>
    <div >
        <componentsHistory></componentsHistory>
        <div class="top-text">
            <h2>你好，有问题尽管问！</h2>

            <span class="top-state">仅限于<span class="top-state2">应用内的指标分析</span>哟</span>
        </div>
        <div style="margin-top:2vh ;">
            <div class="box" @click="gotoChat">
                <div>
                    <span class="box-text">点这里,你可以开始提问了</span>
                </div>
                <div class="box-bottom">
                    <div class="left">
                        <div style="padding-top: 4px;">
                            <span class="spanSty">快速回答</span>
                            <span>深度思考</span>
                        </div>



                    </div>
                    <div class="right">
                        <!-- <img :src="require('@/assets/images/wel/yuyin.svg')" alt=""> -->

                        <!-- <i style="width: 0.5px;height: 5px;border: 1px solid #c5c7ca;margin: 8px;position: relative;bottom: 6px;"></i> -->
                        <img :src="require('@/assets/images/wel/fas.svg')" alt="">

                        <!-- <div ></div> -->

                    </div>
                </div>
            </div>
        </div>
        <div class="text-hot flex">
            <div class="ti-top">
                <span>热门关键词：</span>
            </div>
            <div class="ti-text">
                <span style="word-break: keep-all; " v-for="(item, index) in keywordData" :key="index">{{
                    item.word }} {{ index != keywordData.length - 1 ? '、' : '' }}</span>
            </div>

        </div>
        <div class="box-tj">
            <div>
                <!-- <span class="text">近期热门话题：</span> -->
                <img :src="require('@/assets/images/wel/huati.svg')" alt="">
            </div>
            <div class="box-list">
                <li v-for="(item, index) in dataList" :key="index" @click="gotoChat(item)"><span
                        style="margin-right: 5px;" :class="lapili(index)"> <span class="text-index">{{ index +
                            1 }} </span>
                    </span> {{
                        item.question }}
                </li>


            </div>

        </div>


    </div>
</template>

<script>
import { module1 } from 'vue'
import {
    historyrecord
} from "@/api/burialPoint/burialPoint.js";
import { createdSession } from "@/api/home/home.js";
import componentsHistory from "./module/componentsHistory.vue";
import { keywordTop5, questionTop5 } from "@/api/home/home.js";
import { burialPoint } from "@/utils/util";

import { create } from 'sortablejs';
export default {
    components: {
        componentsHistory
    },
    inject: ["main"],
    provide() {
        return {
            main: this,
        };
    },
    data() {

        return {
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
            sessionId: '',
            agentId: '',
            sessionIdKey: '',
            agentIdKey: '',
            userInfo: JSON.parse(sessionStorage.getItem('userInfo')) || { UserId: '15205009333', name: 'zhou' },
            keywordData: [],
            startTime: Date.now()
        }
    },

    computed: {


    },
    watch: {

    },

    created() {
        this.getPoint()// this.getSession()
    },

    mounted() {
        // 监听屏幕旋转
        window.addEventListener("orientationchange", this.handleOrientationChange);
        this.getList()
        this.getKeywordTop5()
        this.getQuestionTop5()
    },
    beforeDestroy() {
        // 离开页面时移除监听
        window.removeEventListener("orientationchange", this.handleOrientationChange);
    },
    methods: {

        lapili(index) {
            let clsName = ''
            if (index == 0) clsName = 'target'
            if (index == 1) clsName = 'target2'
            if (index == 2) clsName = 'target3'
            return clsName
        },
        gotoChat(item) {

            this.$router.push({
                path: "/aiDialogue/index",
                query: {
                    sessionId: this.sessionId,
                    agentId: this.agentId,
                    sessionIdKey: this.sessionIdKey,
                    agentIdKey: this.agentIdKey,
                    value: item.question
                }
            })
        },
        getList() {
            let obj = {

            }
            createdSession(obj).then((res) => {
                this.sessionIdKey = res.data.id

            })
        },

        // getSession() {
        //     let obj = {
        //         "userId": this.userInfo.UserId,
        //         "title": "ChatBI无法再简单版本-配置Q2SQL",
        //     }
        //     createdSession(obj).then((res) => {
        //         this.sessionId = res.data.sessionId
        //         this.agentId = res.data.agentId
        //     })
        // },
        getKeywordTop5() {
            keywordTop5().then((res) => {
                this.keywordData = res.data
            })
        },
        getQuestionTop5() {
            questionTop5().then((res) => {
                this.dataList = res.data
            })
        },
        getPoint() {
            let currentTime = Date.now()
            const params = {
                dim: 0,
                field: this.selectName,
                card: this.selectName,
                home_page: 'AI',
                stayTime: parseInt((currentTime - this.startTime) / 1000),
            }
            burialPoint(params)
        },
    }
}
</script>

<style scoped lang="less">
.top-text {
    margin-top: 80px;
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


.box {
    margin-left: auto;
    margin-right: auto;
    width: 88%;
    height: 80px;
    border-radius: 10px;
    position: relative;

    &::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        border-radius: inherit;
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
        font-size: 15px;
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
            width: 80%;


            span {
                display: block;
                background: #eff6ff;
                font-size: 12px;
                color: #767b7e;
                border-radius: 5px;
                padding: 3px;
                width: 80px;
                text-align: center;
                float: left;
            }

            .spanSty {
                color: #0881fa;
                border: 1px solid #0881fa;
                margin-right: 10px;
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

}

.text-hot {
    margin-top: 2vh;
    text-align: right;
    font-size: 14px;
    color: #5b5353;
    padding-top: 10px;
    margin: 0px auto;
    width: 88%;

    .ti-top {
       
        width: 95px;
    }
    .ti-text{
        flex: 1;
    }
}

.box-tj {
    margin-top: 2vh;
    margin-left: auto;
    margin-right: auto;
    width: 88%;
    // height: 80px;
    background: #eff6ff;
    border-radius: 10px;
    padding: 10px;
    padding-left: 20px;

    img {
        width: 125px;
        height: 32px;
        margin-left: -2px;
    }

    .box-list {
        margin-top: -10px;
    }
}

li {
    font-size: 15px;
    margin: 5px 0px;
    list-style-type: none;
    color: #4B5563;

    /* 移除默认的列表样式 */
    .target {
        color: #0881FA;
    }

    .target2 {
        color: #17CA5C;
    }

    .target3 {
        color: #F59E0B;
    }

    .text-index {
        font-weight: 600;
    }
}

.text {
    font-weight: 600;
    //文本渐变色
    background: -webkit-linear-gradient(right, #feb47b, #0881fa, );
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
</style>