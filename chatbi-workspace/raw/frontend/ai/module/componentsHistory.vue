<template>
    <div class="ico">
        <div class=" flex justify-between">
            <div class="left">
                <img :src="imgs" alt="" @click="showPopup">

            </div>
            <div class="right">
                <img v-if="$route.name != 'AI'" :src="imgs2" alt="" class="btn-img" @click="newAdd">
            </div>
        </div>

        <van-popup v-model="show" position="left" :style="{ width: '70%', height: '100%' }">
            <div class="text pl-2">
                <ul>
                    <li class="title-sty">今日</li>
                    <li v-for="item in listItem">
                        <span v-if="item.titleTime == '今日'" style="line-height: 35px;"
                            @click="gotoAi(item.sessionUuid)">{{
                                item.question }}</span>
                    </li>
                </ul>
                <ul>
                    <li class="title-sty">昨日</li>
                    <li v-for="item in listItem">
                        <span v-if="item.titleTime == '昨日'" style="line-height: 35px;"
                            @click="gotoAi(item.sessionUuid)">{{
                                item.question }}</span>
                    </li>
                </ul>
                <ul>
                    <li class="title-sty">一个月内</li>
                    <li v-for="item in listItem">
                        <span v-if="item.titleTime == '一个月内'" style="line-height: 35px;"
                            @click="gotoAi(item.sessionUuid)">{{ item.question }}</span>
                    </li>

                </ul>
            </div>
        </van-popup>
    </div>
</template>

<script>
import dayjs from 'dayjs';
import { recordList } from "@/api/home/home.js";

export default {

    inject: ["main"],
    components: {},
    data() {
        return {
            dataList: [

            ],
            show: false,
            listItem: [
                {
                    title: '123',
                    content: '8月传祺终端',
                    time: '2025-05-13'
                },
                {
                    title: '123',
                    content: '集团8月终端',
                    time: '2025-05-13'
                },
                {
                    title: '123',
                    content: '埃安8月产销情况',
                    time: '2025-05-12'
                },
                {
                    title: '123',
                    content: '昊铂8月产销情况',
                    time: '2025-05-12'
                },
                {
                    title: '123',
                    content: '昊铂8月产销情况1',
                    time: '2025-05-05'
                },
                {
                    title: '123',
                    content: '昊铂8月产销情况2',
                    time: '2025-05-04'
                },
                {
                    title: '123',
                    content: '昊铂8月产销情况3',
                    time: '2025-05-07'
                },
            ],
            userInfo: JSON.parse(sessionStorage.getItem('userInfo')) || { UserId: '15205009333', name: 'zhou' },
        }
    },

    computed: {

        imgs() {
            return require('@/assets/images/wel/lishi.svg')
        },
        imgs2() {
            return require('@/assets/images/wel/xinduihua.svg')
        }
    },
    watch: {

    },


    mounted() {

    },
    methods: {
        showPopup() {
            this.show = true;
            this.getData()
        },
        getData() {

            let obj = {
                userId: this.userInfo.UserId,
            }
            let NewTime = dayjs().format('YYYY-MM-DD') //当天
            let qiantime = dayjs().subtract(1, 'day').format('YYYY-MM-DD'); //前一天
            recordList(obj).then((res) => {
                this.listItem = res.data.reverse();//倒序
                 
                this.listItem.forEach((item) => {
                    item.time = dayjs(item.createTime).format('YYYY-MM-DD')


                    if (NewTime == item.time) {
                        item.titleTime = '今日'
                    } else if (qiantime == item.time) {
                        item.titleTime = '昨日'
                    } else {
                        item.titleTime = '一个月内'
                    }
                })

            })




        },
        newAdd() {//新建对话
            this.$emit('newAdd')
        },
        gotoAi(item) {
            let url = this.$route.path

            if (url == '/aiDialogue/index') {
                this.$emit('getLiShi', item)
            } else {
                this.$router.push({
                    path: "/aiDialogue/index",
                    query: {
                        sessionId: this.main.sessionId,
                        agentId: this.main.agentId,
                        sessionUuid: item
                    }
                })
            }
            this.show = false
        }
    }
}
</script>

<style scoped lang="less">
.ico {
    font-size: 20px;
    color: #b70606;
    margin-top: 10px;
    margin-left: 10px;

}

.btn-img {
    width: 62px;
    height: 34px;
    font-size: 10px;
    margin-top: -6px;
    margin-right: 5px;
}

.text {
    margin: 20px 10px 10px 10px;

    ul {
        margin-bottom: 10px;
    }

    .title-sty {
        font-size: 13px;
        color: #94A3B8;
    }

    span {
        margin-bottom: 10px;
        font-size: 15px;
        color: #090a0a;
    }
}

</style>